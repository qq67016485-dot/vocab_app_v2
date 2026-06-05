"""Graphic novel script generation (Step 7A) and substep restart entry point."""
import json
import logging
import time

from vocabulary.models import (
    ClozeItem, GenerationJob, GenerationJobLog, GraphicNovel, GraphicNovelPage,
)
from vocabulary.services.canon_service import (
    collapse_markdown,
    load_character_sheet,
    load_pairing_dynamics,
    load_script_character_sheets,
    load_team_selector_dynamics,
    load_team_selector_heroes,
    load_vault_script_context,
    load_vault_summary_premises,
    sample_team_options,
)
from vocabulary.services.generation.constants import (
    GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES,
    GRAPHIC_NOVEL_SCRIPT_TEMPLATES,
    GRAPHIC_NOVEL_SUBSTEPS,
    page_count_for_word_count,
)
from vocabulary.services.generation.graphic_novel_helpers import (
    _generate_secondary_character_anchors,
    _graphic_novel_word_summary,
    _lexi_legends_age_band,
    _load_substep_artifact,
    _page_vocab_words,
    _run_graphic_novel_substep,
)
from vocabulary.services.generation.graphic_novel_validators import (
    SubstepContext,
    _validate_graphic_novel_beat_result,
    _validate_graphic_novel_cloze_result,
    _validate_graphic_novel_router_result,
    _validate_graphic_novel_scoring_result,
    _validate_graphic_novel_script_result,
    _validate_graphic_novel_team_result,
    _validate_words_data_covers_pack,
)
from vocabulary.services.generation.helpers import _content_lexile, _log_step
from vocabulary.services.generation.llm_config_service import get_step_config
import vocabulary.services.llm_service as _llm_service

logger = logging.getLogger(__name__)


def _completed_substep_keys_for_pack(job, pack):
    """Set of GN substep keys that have a COMPLETED log for this pack.

    The COMPLETED log — not artifact presence — is the authoritative signal:
    ``_run_graphic_novel_substep`` writes an artifact *before* validation, so a
    validation failure can leave a stale artifact behind without a COMPLETED log.
    """
    return {
        log.output_data.get('substep')
        for log in job.logs.filter(
            step=GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            status=GenerationJob.Status.COMPLETED,
        )
        if isinstance(log.output_data, dict)
        and log.output_data.get('pack_id') == pack.id
        and log.output_data.get('substep')
    }


def _prior_substep_artifacts_exist(job, pack, up_to_idx):
    """True if every substep before ``up_to_idx`` has a readable artifact on disk."""
    for idx in range(up_to_idx):
        if _load_substep_artifact(job, pack, GRAPHIC_NOVEL_SUBSTEPS[idx]) is None:
            return False
    return True


def _resume_substep_index_for_pack(job, pack):
    """Index of the first GN substep that should run for ``pack`` on resume.

    Returns the first substep (in order) without a COMPLETED log — i.e. the one
    that failed or never ran. Returns 0 for a fresh pack (nothing completed yet).
    When every substep completed but the novel never materialised, clamps to the
    final substep so it regenerates the script and rebuilds the novel records.
    """
    completed = _completed_substep_keys_for_pack(job, pack)
    for idx, substep in enumerate(GRAPHIC_NOVEL_SUBSTEPS):
        if substep['key'] not in completed:
            return idx
    return len(GRAPHIC_NOVEL_SUBSTEPS) - 1


def _step_graphic_novel_script(job, packs, words_data):
    """
    Step 7A: Generate a graphic novel script for each pack.

    The script step creates the novel/page records without images so image
    generation can resume independently. Cloze items are generated in a
    dedicated substep using the winning premise as context.
    """
    start = time.time()
    try:
        templates = {
            config['key']: _llm_service.load_prompt_template(config['template'])
            for config in GRAPHIC_NOVEL_SUBSTEPS
        }
        beat_sheet_templates_by_page_count = {
            page_count: _llm_service.load_prompt_template(template_name)
            for page_count, template_name in GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES.items()
        }
        script_templates_by_page_count = {
            page_count: _llm_service.load_prompt_template(template_name)
            for page_count, template_name in GRAPHIC_NOVEL_SCRIPT_TEMPLATES.items()
        }
        total_novels = 0
        total_cloze = 0
        artifact_references = []
        logger.info("Graphic novel script generation started for job %s", job.id)

        if not packs:
            raise RuntimeError(
                f"No packs found for job {job.id}. "
                "The PACK_CREATION step must run before graphic novel generation."
            )

        for pack in packs:
            existing_novel = pack.graphic_novels.filter(channel='5page').first()
            if existing_novel and existing_novel.pages.exists():
                logger.info("Pack '%s' already has a graphic novel with pages, skipping", pack.label)
                continue
            if existing_novel:
                logger.info("Pack '%s' has a novel but no pages, deleting and regenerating", pack.label)
                existing_novel.delete()

            # Resume support: if earlier substeps for this pack already completed
            # (a later substep failed), pick up from the first incomplete substep
            # instead of restarting from team selection. Requires the prior
            # substeps' artifacts on disk to reconstruct context.
            resume_idx = _resume_substep_index_for_pack(job, pack)
            if resume_idx > 0 and _prior_substep_artifacts_exist(job, pack, resume_idx):
                resume_key = GRAPHIC_NOVEL_SUBSTEPS[resume_idx]['key']
                logger.info(
                    "Pack '%s' resuming graphic novel script from substep '%s' (index %d)",
                    pack.label, resume_key, resume_idx,
                )
                restart_graphic_novel_from_substep(job, pack.id, resume_key, words_data)
                total_novels += 1
                total_cloze += ClozeItem.objects.filter(pack=pack).count()
                artifact_references.append({
                    'pack_id': pack.id,
                    'pack_label': pack.label,
                    'substep': resume_key,
                    'artifact_path': '',
                    'resumed_from_substep': resume_key,
                })
                continue

            logger.info("Generating graphic novel script for pack '%s'", pack.label)

            pack_word_texts = list(pack.items.values_list('word__text', flat=True))
            pack_word_keys = {text.lower() for text in pack_word_texts}
            pack_words_data = [
                wd for wd in words_data
                if wd.get('term', '').lower() in pack_word_keys
            ]
            _validate_words_data_covers_pack(pack, pack_words_data)

            required_page_count = page_count_for_word_count(len(pack_words_data))
            content_lexile = _content_lexile(job)
            base_input = {
                'pack_label': pack.label,
                'text_type': pack.text_type,
                'target_lexile': content_lexile,
                'required_page_count': required_page_count,
                'words': _graphic_novel_word_summary(pack_words_data),
            }
            input_summary = {
                'pack_label': pack.label,
                'text_type': pack.text_type,
                'target_lexile': content_lexile,
                'required_page_count': required_page_count,
                'word_count': len(pack_words_data),
                'words': [wd.get('term', '') for wd in pack_words_data],
            }

            team_options = sample_team_options()
            unique_heroes = list({
                name for team in team_options for name in team
            })
            hero_summaries = load_team_selector_heroes(unique_heroes)
            pairing_dynamics = load_team_selector_dynamics(team_options)

            team_user_input = {
                'pack_label': pack.label,
                'text_type': pack.text_type,
                'target_lexile': content_lexile,
                'age_band': _lexi_legends_age_band(content_lexile),
                'words': _graphic_novel_word_summary(pack_words_data),
                'team_options': team_options,
                'hero_summaries': hero_summaries,
                'pairing_dynamics': pairing_dynamics,
            }
            team_result, team_path = _run_graphic_novel_substep(
                job,
                pack,
                GRAPHIC_NOVEL_SUBSTEPS[0],
                get_step_config('gn_team_selection')['primary'],
                templates['team_selection'],
                json.dumps(team_user_input, ensure_ascii=False, indent=2),
                input_summary,
                validator=_validate_graphic_novel_team_result,
            )
            artifact_references.append({
                'pack_id': pack.id,
                'pack_label': pack.label,
                'substep': 'team_selection',
                'artifact_path': team_path,
            })
            novel_metadata = {
                'away_team': team_result.get('selected_away_team', []),
                'age_band': _lexi_legends_age_band(content_lexile),
                'vault_framing': team_result.get('vault_framing', False),
                'review_artifact_type': '',
            }
            away_team = team_result.get('selected_away_team', [])
            age_band = _lexi_legends_age_band(content_lexile)
            character_sheets = ' | '.join(
                collapse_markdown(load_character_sheet(name, age_band)) for name in away_team
            )
            script_character_sheets = load_script_character_sheets(away_team)
            lexi_context = {
                **novel_metadata,
                'team_rationale': team_result.get('team_rationale', ''),
                'character_sheets': character_sheets,
                'vault_script_context': load_vault_script_context(
                    team_result.get('vault_framing', False)
                ),
            }
            if len(away_team) == 2:
                lexi_context['pairing_dynamics'] = load_pairing_dynamics(away_team)

            router_lexi_context = {
                **novel_metadata,
                'team_rationale': team_result.get('team_rationale', ''),
                'character_sheets': script_character_sheets,
                'vault_context': load_vault_summary_premises(
                    team_result.get('vault_framing', False)
                ),
            }
            if len(away_team) == 2:
                router_lexi_context['pairing_dynamics'] = load_team_selector_dynamics(
                    [away_team]
                )

            router_user_input = {
                **base_input,
                'lexi_legends': router_lexi_context,
            }
            router_result, router_path = _run_graphic_novel_substep(
                job,
                pack,
                GRAPHIC_NOVEL_SUBSTEPS[1],
                get_step_config('gn_router_premises')['primary'],
                templates['router_premises'],
                json.dumps(router_user_input, ensure_ascii=False, indent=2),
                input_summary,
                validator=_validate_graphic_novel_router_result,
            )
            artifact_references.append({
                'pack_id': pack.id,
                'pack_label': pack.label,
                'substep': 'router_premises',
                'artifact_path': router_path,
            })

            scoring_input = {
                **base_input,
                'lexi_legends': router_lexi_context,
                'router_result': {
                    'audience_age_band': router_result.get('audience_age_band', ''),
                    'tone': router_result.get('tone', ''),
                    'genre': router_result.get('genre', ''),
                    'narrative_approach': router_result.get('narrative_approach', ''),
                    'premises': router_result.get('premises', []),
                },
            }
            scoring_result, scoring_path = _run_graphic_novel_substep(
                job,
                pack,
                GRAPHIC_NOVEL_SUBSTEPS[2],
                get_step_config('gn_premise_scoring')['primary'],
                templates['premise_scoring'],
                json.dumps(scoring_input, ensure_ascii=False, indent=2),
                input_summary,
                validator=_validate_graphic_novel_scoring_result,
                ctx=SubstepContext(router_result=router_result),
            )
            artifact_references.append({
                'pack_id': pack.id,
                'pack_label': pack.label,
                'substep': 'premise_scoring',
                'artifact_path': scoring_path,
            })

            winning_premise = scoring_result.get('winning_premise', {})
            winning_premise_id = scoring_result.get('winning_premise_id', '')
            for premise in router_result.get('premises', []):
                if premise.get('id') == winning_premise_id:
                    winning_premise = premise
                    break

            # Page count is derived from the pack's word count, not the LLM's
            # choice. The router is told the required length, but we force it
            # here so the rule holds regardless of what the model returns.
            page_count = required_page_count
            page_count_raw = winning_premise.get('page_count')
            if page_count_raw != page_count:
                logger.info(
                    "Pack '%s' (%d words): forcing page_count to %d "
                    "(winning premise declared %r).",
                    pack.label, len(pack_words_data), page_count, page_count_raw,
                )
            winning_premise['page_count'] = page_count

            cloze_input = {
                **base_input,
                'winning_premise': winning_premise,
            }
            cloze_result, cloze_path = _run_graphic_novel_substep(
                job,
                pack,
                GRAPHIC_NOVEL_SUBSTEPS[3],
                get_step_config('gn_cloze_gen')['primary'],
                templates['cloze_generation'],
                json.dumps(cloze_input, ensure_ascii=False, indent=2),
                input_summary,
                validator=_validate_graphic_novel_cloze_result,
                ctx=SubstepContext.from_input_summary(input_summary),
            )
            artifact_references.append({
                'pack_id': pack.id,
                'pack_label': pack.label,
                'substep': 'cloze_generation',
                'artifact_path': cloze_path,
            })

            beat_input = {
                **base_input,
                'lexi_legends': router_lexi_context,
                'winning_premise': winning_premise,
            }
            beat_ctx = SubstepContext.from_input_summary(
                input_summary,
                winning_premise=winning_premise,
                selected_away_team=team_result.get('selected_away_team', []),
            )
            beat_template_name = GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES[page_count]
            beat_template = beat_sheet_templates_by_page_count[page_count]
            beat_result, beat_path = _run_graphic_novel_substep(
                job,
                pack,
                GRAPHIC_NOVEL_SUBSTEPS[4],
                get_step_config('gn_beat_sheet')['primary'],
                beat_template,
                json.dumps(beat_input, ensure_ascii=False, indent=2),
                input_summary,
                validator=_validate_graphic_novel_beat_result,
                prompt_template_name=beat_template_name,
                ctx=beat_ctx,
            )
            artifact_references.append({
                'pack_id': pack.id,
                'pack_label': pack.label,
                'substep': 'beat_sheet_vocab_roles',
                'artifact_path': beat_path,
            })
            novel_metadata['review_artifact_type'] = beat_result.get('review_artifact_type', '')
            lexi_context['review_artifact_type'] = novel_metadata['review_artifact_type']
            if 'pairing_dynamics' in lexi_context:
                lexi_context['pairing_dynamics'] = load_team_selector_dynamics(
                    [away_team]
                )

            final_input = {
                **base_input,
                'lexi_legends': lexi_context,
                'winning_premise': winning_premise,
                'beat_sheet': beat_result.get('beat_sheet', []),
                'vocab_roles': beat_result.get('vocab_roles', {}),
                'ink_usage': beat_result.get('ink_usage', []),
                'review_artifact_type': beat_result.get('review_artifact_type', ''),
            }
            script_ctx = SubstepContext.from_input_summary(
                input_summary,
                winning_premise=winning_premise,
            )
            script_template_name = GRAPHIC_NOVEL_SCRIPT_TEMPLATES[page_count]
            script_template = script_templates_by_page_count[page_count]
            result, final_path = _run_graphic_novel_substep(
                job,
                pack,
                GRAPHIC_NOVEL_SUBSTEPS[5],
                get_step_config('gn_final_script')['primary'],
                script_template,
                json.dumps(final_input, ensure_ascii=False, indent=2),
                input_summary,
                validator=_validate_graphic_novel_script_result,
                prompt_template_name=script_template_name,
                ctx=script_ctx,
            )
            artifact_references.append({
                'pack_id': pack.id,
                'pack_label': pack.label,
                'substep': 'final_script_self_check',
                'artifact_path': final_path,
            })

            novel_metadata['page_count'] = page_count

            secondary_anchors = _generate_secondary_character_anchors(
                result, novel_metadata,
                get_step_config('gn_final_script')['primary'],
            )
            if secondary_anchors:
                novel_metadata['secondary_character_anchors'] = secondary_anchors

            GraphicNovel.objects.filter(pack=pack, channel='5page').delete()
            novel = GraphicNovel.objects.create(
                pack=pack,
                title=result.get('title', f'{pack.label} Graphic Novel'),
                synopsis=result.get('synopsis', ''),
                characters=result.get('characters', []),
                metadata=novel_metadata,
                style_prompt=result.get(
                    'style_prompt',
                    result.get('style_notes', 'Middle-grade graphic novel art with clear readable lettering.'),
                ),
                reading_level=result.get('reading_level', content_lexile),
            )
            total_novels += 1

            for idx, page_data in enumerate(result.get('pages', []), 1):
                panel_descriptions = page_data.get('panels', [])
                GraphicNovelPage.objects.create(
                    novel=novel,
                    page_number=page_data.get('page_number', idx),
                    panel_count=page_data.get('panel_count', len(panel_descriptions) or 1),
                    layout_description=page_data.get('layout_description', ''),
                    panel_descriptions=panel_descriptions,
                    characters_featured=page_data.get('characters_featured', []),
                    setting_key=page_data.get('setting_key', ''),
                    vault_zone=page_data.get('vault_zone', ''),
                    is_vault_page=page_data.get('is_vault_page', False),
                    vocab_words_used=_page_vocab_words(page_data),
                )

            review_page_number = len(result.get('pages', [])) + 1
            all_vocab_words = [wd['term'] for wd in pack_words_data]
            story_characters = []
            for page_data in result.get('pages', []):
                for char in page_data.get('characters_featured', []):
                    if char not in story_characters:
                        story_characters.append(char)
            review_characters = story_characters[:2] if story_characters else []
            GraphicNovelPage.objects.create(
                novel=novel,
                page_number=review_page_number,
                panel_count=1,
                layout_description='Vocabulary review word cards spread',
                panel_descriptions=[],
                vocab_words_used=all_vocab_words,
                characters_featured=review_characters,
                setting_key='the_vault' if novel_metadata.get('vault_framing') else 'review',
                vault_zone='review_artifact',
                is_vault_page=novel_metadata.get('vault_framing', False),
                is_review_page=True,
            )

            word_map = {
                item.word.text.lower(): item.word
                for item in pack.items.select_related('word').all()
            }
            for idx, ci in enumerate(cloze_result.get('cloze_items', [])):
                term = ci.get('term', '').lower()
                word = word_map.get(term)
                if not word:
                    continue

                ClozeItem.objects.create(
                    pack=pack,
                    word=word,
                    sentence_text=ci.get('sentence_text', ''),
                    correct_answer=ci.get('correct_answer', ''),
                    distractors=ci.get('distractors', []),
                    order=idx,
                )
                total_cloze += 1

        job.graphic_novels_created = GraphicNovel.objects.filter(pack__in=packs).count()
        job.cloze_items_created = ClozeItem.objects.filter(pack__in=packs).count()
        job.save(update_fields=['graphic_novels_created', 'cloze_items_created'])

        duration = time.time() - start
        logger.info(
            "Graphic novel script generation completed for job %s: %d novels, %d cloze items",
            job.id, total_novels, total_cloze,
        )
        _log_step(
            job, GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data={
                'prompt_template': 'graphic_novel_script_pipeline',
                'graphic_novels_created': total_novels,
                'cloze_items_created': total_cloze,
                'artifact_references': artifact_references,
            },
        )

    except Exception as exc:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
            GenerationJob.Status.FAILED,
            duration=duration,
            error_message=str(exc),
        )
        raise


def restart_graphic_novel_from_substep(job, pack_id, substep_key, words_data):
    """
    Restart graphic novel script generation for a single pack from a specific substep.

    Loads prior substep artifacts to reconstruct context, deletes existing novel/cloze
    for the pack, then runs from the target substep onward.
    """
    from vocabulary.models import WordPack
    start = time.time()

    substep_keys = [s['key'] for s in GRAPHIC_NOVEL_SUBSTEPS]
    if substep_key not in substep_keys:
        raise ValueError(f"Invalid substep key: {substep_key}. Valid: {substep_keys}")

    start_idx = substep_keys.index(substep_key)
    pack = WordPack.objects.prefetch_related('items__word').get(id=pack_id, word_set=job.word_set)

    if hasattr(pack, 'graphic_novels'):
        pack.graphic_novels.filter(channel='5page').delete()
    ClozeItem.objects.filter(pack=pack).delete()

    pack_word_texts = list(pack.items.values_list('word__text', flat=True))
    pack_word_keys = {text.lower() for text in pack_word_texts}
    pack_words_data = [
        wd for wd in words_data
        if wd.get('term', '').lower() in pack_word_keys
    ]
    _validate_words_data_covers_pack(pack, pack_words_data)

    required_page_count = page_count_for_word_count(len(pack_words_data))
    content_lexile = _content_lexile(job)
    base_input = {
        'pack_label': pack.label,
        'text_type': pack.text_type,
        'target_lexile': content_lexile,
        'required_page_count': required_page_count,
        'words': _graphic_novel_word_summary(pack_words_data),
    }
    input_summary = {
        'pack_label': pack.label,
        'text_type': pack.text_type,
        'target_lexile': content_lexile,
        'required_page_count': required_page_count,
        'word_count': len(pack_words_data),
        'words': [wd.get('term', '') for wd in pack_words_data],
    }

    templates = {
        config['key']: _llm_service.load_prompt_template(config['template'])
        for config in GRAPHIC_NOVEL_SUBSTEPS
    }
    beat_sheet_templates_by_page_count = {
        page_count: _llm_service.load_prompt_template(template_name)
        for page_count, template_name in GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES.items()
    }
    script_templates_by_page_count = {
        page_count: _llm_service.load_prompt_template(template_name)
        for page_count, template_name in GRAPHIC_NOVEL_SCRIPT_TEMPLATES.items()
    }

    team_result = None
    router_result = None
    scoring_result = None
    cloze_result = None
    beat_result = None
    novel_metadata = {}
    lexi_context = {}
    router_lexi_context = {}

    for idx in range(start_idx):
        artifact_response = _load_substep_artifact(job, pack, GRAPHIC_NOVEL_SUBSTEPS[idx])
        if artifact_response is None:
            raise ValueError(
                f"Cannot restart from '{substep_key}': missing artifact for prior substep "
                f"'{GRAPHIC_NOVEL_SUBSTEPS[idx]['key']}'. Run from an earlier substep."
            )
        if idx == 0:
            team_result = artifact_response
        elif idx == 1:
            router_result = artifact_response
        elif idx == 2:
            scoring_result = artifact_response
        elif idx == 3:
            cloze_result = artifact_response
        elif idx == 4:
            beat_result = artifact_response

    if team_result:
        novel_metadata = {
            'away_team': team_result.get('selected_away_team', []),
            'age_band': _lexi_legends_age_band(content_lexile),
            'vault_framing': team_result.get('vault_framing', False),
            'review_artifact_type': '',
        }
        away_team = team_result.get('selected_away_team', [])
        age_band = _lexi_legends_age_band(content_lexile)
        character_sheets = ' | '.join(
            collapse_markdown(load_character_sheet(name, age_band)) for name in away_team
        )
        script_character_sheets = load_script_character_sheets(away_team)
        lexi_context = {
            **novel_metadata,
            'team_rationale': team_result.get('team_rationale', ''),
            'character_sheets': character_sheets,
            'vault_script_context': load_vault_script_context(
                team_result.get('vault_framing', False)
            ),
        }
        if len(away_team) == 2:
            lexi_context['pairing_dynamics'] = load_pairing_dynamics(away_team)

        router_lexi_context = {
            **novel_metadata,
            'team_rationale': team_result.get('team_rationale', ''),
            'character_sheets': script_character_sheets,
            'vault_context': load_vault_summary_premises(
                team_result.get('vault_framing', False)
            ),
        }
        if len(away_team) == 2:
            router_lexi_context['pairing_dynamics'] = load_team_selector_dynamics(
                [away_team]
            )

    if beat_result:
        novel_metadata['review_artifact_type'] = beat_result.get('review_artifact_type', '')
        lexi_context['review_artifact_type'] = novel_metadata['review_artifact_type']

    if start_idx <= 0:
        team_options = sample_team_options()
        unique_heroes = list({
            name for team in team_options for name in team
        })
        hero_summaries = load_team_selector_heroes(unique_heroes)
        pairing_dynamics = load_team_selector_dynamics(team_options)

        team_user_input = {
            'pack_label': pack.label,
            'text_type': pack.text_type,
            'target_lexile': content_lexile,
            'age_band': _lexi_legends_age_band(content_lexile),
            'words': _graphic_novel_word_summary(pack_words_data),
            'team_options': team_options,
            'hero_summaries': hero_summaries,
            'pairing_dynamics': pairing_dynamics,
        }
        team_result, _ = _run_graphic_novel_substep(
            job, pack, GRAPHIC_NOVEL_SUBSTEPS[0], get_step_config('gn_team_selection')['primary'],
            templates['team_selection'],
            json.dumps(team_user_input, ensure_ascii=False, indent=2),
            input_summary,
            validator=_validate_graphic_novel_team_result,
        )
        novel_metadata = {
            'away_team': team_result.get('selected_away_team', []),
            'age_band': _lexi_legends_age_band(content_lexile),
            'vault_framing': team_result.get('vault_framing', False),
            'review_artifact_type': '',
        }
        away_team = team_result.get('selected_away_team', [])
        age_band = _lexi_legends_age_band(content_lexile)
        character_sheets = ' | '.join(
            collapse_markdown(load_character_sheet(name, age_band)) for name in away_team
        )
        script_character_sheets = load_script_character_sheets(away_team)
        lexi_context = {
            **novel_metadata,
            'team_rationale': team_result.get('team_rationale', ''),
            'character_sheets': character_sheets,
            'vault_script_context': load_vault_script_context(
                team_result.get('vault_framing', False)
            ),
        }
        if len(away_team) == 2:
            lexi_context['pairing_dynamics'] = load_pairing_dynamics(away_team)
        router_lexi_context = {
            **novel_metadata,
            'team_rationale': team_result.get('team_rationale', ''),
            'character_sheets': script_character_sheets,
            'vault_context': load_vault_summary_premises(
                team_result.get('vault_framing', False)
            ),
        }
        if len(away_team) == 2:
            router_lexi_context['pairing_dynamics'] = load_team_selector_dynamics(
                [away_team]
            )

    if start_idx <= 1:
        router_user_input = {
            **base_input,
            'lexi_legends': router_lexi_context,
        }
        router_result, _ = _run_graphic_novel_substep(
            job, pack, GRAPHIC_NOVEL_SUBSTEPS[1], get_step_config('gn_router_premises')['primary'],
            templates['router_premises'],
            json.dumps(router_user_input, ensure_ascii=False, indent=2),
            input_summary,
            validator=_validate_graphic_novel_router_result,
        )

    if start_idx <= 2:
        scoring_input = {
            **base_input,
            'lexi_legends': router_lexi_context,
            'router_result': {
                'audience_age_band': router_result.get('audience_age_band', ''),
                'tone': router_result.get('tone', ''),
                'genre': router_result.get('genre', ''),
                'narrative_approach': router_result.get('narrative_approach', ''),
                'premises': router_result.get('premises', []),
            },
        }
        scoring_result, _ = _run_graphic_novel_substep(
            job, pack, GRAPHIC_NOVEL_SUBSTEPS[2], get_step_config('gn_premise_scoring')['primary'],
            templates['premise_scoring'],
            json.dumps(scoring_input, ensure_ascii=False, indent=2),
            input_summary,
            validator=_validate_graphic_novel_scoring_result,
            ctx=SubstepContext(router_result=router_result),
        )

    winning_premise = scoring_result.get('winning_premise', {})
    winning_premise_id = scoring_result.get('winning_premise_id', '')
    for premise in router_result.get('premises', []):
        if premise.get('id') == winning_premise_id:
            winning_premise = premise
            break

    # Page count is derived from the pack's word count, not the LLM's choice
    # (kept in sync with _step_graphic_novel_script).
    page_count = required_page_count
    page_count_raw = winning_premise.get('page_count')
    if page_count_raw != page_count:
        logger.info(
            "Restart pack '%s' (%d words): forcing page_count to %d "
            "(winning premise declared %r).",
            pack.label, len(pack_words_data), page_count, page_count_raw,
        )
    winning_premise['page_count'] = page_count

    if start_idx <= 3:
        cloze_input = {
            **base_input,
            'winning_premise': winning_premise,
        }
        cloze_result, _ = _run_graphic_novel_substep(
            job, pack, GRAPHIC_NOVEL_SUBSTEPS[3], get_step_config('gn_cloze_gen')['primary'],
            templates['cloze_generation'],
            json.dumps(cloze_input, ensure_ascii=False, indent=2),
            input_summary,
            validator=_validate_graphic_novel_cloze_result,
            ctx=SubstepContext.from_input_summary(input_summary),
        )

    if start_idx <= 4:
        beat_input = {
            **base_input,
            'lexi_legends': router_lexi_context,
            'winning_premise': winning_premise,
        }
        beat_ctx = SubstepContext.from_input_summary(
            input_summary,
            winning_premise=winning_premise,
            selected_away_team=team_result.get('selected_away_team', []),
        )
        beat_template_name = GRAPHIC_NOVEL_BEAT_SHEET_TEMPLATES[page_count]
        beat_template = beat_sheet_templates_by_page_count[page_count]
        beat_result, _ = _run_graphic_novel_substep(
            job, pack, GRAPHIC_NOVEL_SUBSTEPS[4], get_step_config('gn_beat_sheet')['primary'],
            beat_template,
            json.dumps(beat_input, ensure_ascii=False, indent=2),
            input_summary,
            validator=_validate_graphic_novel_beat_result,
            prompt_template_name=beat_template_name,
            ctx=beat_ctx,
        )
        novel_metadata['review_artifact_type'] = beat_result.get('review_artifact_type', '')
        lexi_context['review_artifact_type'] = novel_metadata['review_artifact_type']
        if 'pairing_dynamics' in lexi_context:
            away_team = novel_metadata.get('away_team', [])
            lexi_context['pairing_dynamics'] = load_team_selector_dynamics(
                [away_team]
            )

    final_input = {
        **base_input,
        'lexi_legends': lexi_context,
        'winning_premise': winning_premise,
        'beat_sheet': beat_result.get('beat_sheet', []),
        'vocab_roles': beat_result.get('vocab_roles', {}),
        'ink_usage': beat_result.get('ink_usage', []),
        'review_artifact_type': beat_result.get('review_artifact_type', ''),
    }
    final_validator_summary = {
        **input_summary,
        'winning_premise': winning_premise,
    }
    script_ctx = SubstepContext.from_input_summary(
        final_validator_summary,
        winning_premise=winning_premise,
    )
    script_template_name = GRAPHIC_NOVEL_SCRIPT_TEMPLATES[page_count]
    script_template = script_templates_by_page_count[page_count]
    result, _ = _run_graphic_novel_substep(
        job, pack, GRAPHIC_NOVEL_SUBSTEPS[5], get_step_config('gn_final_script')['primary'],
        script_template,
        json.dumps(final_input, ensure_ascii=False, indent=2),
        input_summary,
        validator=_validate_graphic_novel_script_result,
        prompt_template_name=script_template_name,
        ctx=script_ctx,
    )

    novel_metadata['page_count'] = page_count

    secondary_anchors = _generate_secondary_character_anchors(
        result, novel_metadata,
        get_step_config('gn_final_script')['primary'],
    )
    if secondary_anchors:
        novel_metadata['secondary_character_anchors'] = secondary_anchors

    novel = GraphicNovel.objects.create(
        pack=pack,
        title=result.get('title', f'{pack.label} Graphic Novel'),
        synopsis=result.get('synopsis', ''),
        characters=result.get('characters', []),
        metadata=novel_metadata,
        style_prompt=result.get(
            'style_prompt',
            result.get('style_notes', 'Middle-grade graphic novel art with clear readable lettering.'),
        ),
        reading_level=result.get('reading_level', content_lexile),
    )

    for idx, page_data in enumerate(result.get('pages', []), 1):
        panel_descriptions = page_data.get('panels', [])
        GraphicNovelPage.objects.create(
            novel=novel,
            page_number=page_data.get('page_number', idx),
            panel_count=page_data.get('panel_count', len(panel_descriptions) or 1),
            layout_description=page_data.get('layout_description', ''),
            panel_descriptions=panel_descriptions,
            characters_featured=page_data.get('characters_featured', []),
            setting_key=page_data.get('setting_key', ''),
            vault_zone=page_data.get('vault_zone', ''),
            is_vault_page=page_data.get('is_vault_page', False),
            vocab_words_used=_page_vocab_words(page_data),
        )

    review_page_number = len(result.get('pages', [])) + 1
    all_vocab_words = [wd['term'] for wd in pack_words_data]
    story_characters = []
    for page_data in result.get('pages', []):
        for char in page_data.get('characters_featured', []):
            if char not in story_characters:
                story_characters.append(char)
    review_characters = story_characters[:2] if story_characters else []
    GraphicNovelPage.objects.create(
        novel=novel,
        page_number=review_page_number,
        panel_count=1,
        layout_description='Vocabulary review word cards spread',
        panel_descriptions=[],
        vocab_words_used=all_vocab_words,
        characters_featured=review_characters,
        setting_key='the_vault' if novel_metadata.get('vault_framing') else 'review',
        vault_zone='review_artifact',
        is_vault_page=novel_metadata.get('vault_framing', False),
        is_review_page=True,
    )

    word_map = {
        item.word.text.lower(): item.word
        for item in pack.items.select_related('word').all()
    }
    for idx, ci in enumerate(cloze_result.get('cloze_items', [])):
        term = ci.get('term', '').lower()
        word = word_map.get(term)
        if not word:
            continue
        ClozeItem.objects.create(
            pack=pack,
            word=word,
            sentence_text=ci.get('sentence_text', ''),
            correct_answer=ci.get('correct_answer', ''),
            distractors=ci.get('distractors', []),
            order=idx,
        )

    duration = time.time() - start
    logger.info(
        "Graphic novel substep restart completed for job %s pack '%s' from '%s' (%.1fs)",
        job.id, pack.label, substep_key, duration,
    )
    return novel
