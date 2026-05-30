"""Pipeline steps 5-6: Auto-Create Packs and Generate Primers."""
import json
import logging
import math
import time

from django.conf import settings

from vocabulary.models import (
    WordPack, WordPackItem, PrimerCardContent,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation.helpers import (
    _content_lexile, _log_step, _log_metadata,
    _call_llm_with_config,
)
import vocabulary.services.llm_service as _llm_service

logger = logging.getLogger(__name__)


def _validate_llm_pack_grouping(llm_packs, words, num_packs, max_per_pack):
    if len(llm_packs) != num_packs:
        raise ValueError(f"LLM pack grouping must return exactly {num_packs} packs; got {len(llm_packs)}.")

    expected_terms = {word.text.lower() for word in words}
    seen_terms = {}

    for pack_idx, pack_data in enumerate(llm_packs, 1):
        pack_words = pack_data.get('words', [])
        if not pack_words:
            raise ValueError(f"LLM pack grouping returned empty pack {pack_idx}.")
        if len(pack_words) > max_per_pack:
            raise ValueError(
                f"LLM pack grouping pack {pack_idx} has {len(pack_words)} words; max is {max_per_pack}."
            )

        for term in pack_words:
            key = str(term).lower()
            seen_terms.setdefault(key, 0)
            seen_terms[key] += 1

    seen_set = set(seen_terms)
    duplicate_terms = sorted(term for term, count in seen_terms.items() if count > 1)
    if duplicate_terms:
        raise ValueError(f"LLM pack grouping duplicated words: {duplicate_terms}")
    if seen_set != expected_terms:
        raise ValueError(
            f"LLM pack grouping mismatch: missing={expected_terms - seen_set}, extra={seen_set - expected_terms}"
        )



def _fallback_create_sequential_packs(job, words, pack_size):
    packs = []
    num_packs = max(1, math.ceil(len(words) / pack_size))
    for i in range(num_packs):
        chunk = words[i * pack_size:(i + 1) * pack_size]
        pack = WordPack.objects.create(
            word_set=job.word_set,
            label=f"Pack {i + 1}",
            order=i,
        )
        for idx, word in enumerate(chunk):
            WordPackItem.objects.create(pack=pack, word=word, order=idx)
        packs.append(pack)
    return packs


def _step_auto_create_packs(job, words, words_data=None, site_config=None, allow_fallback=False):
    """
    Step 5: Use LLM to group words into semantically related packs.
    Sequential fallback is only used when explicitly allowed by tests/manual
    tooling, because weak packs directly degrade graphic novel quality.
    """
    if site_config is None:
        from vocabulary.services.generation.llm_config_service import get_step_config
        site_config = get_step_config('pack_creation')['primary']
    start = time.time()
    pack_size = settings.GENERATION_WORDS_PER_PACK
    word_map = {w.text.lower(): w for w in words}
    regroup_existing_packs = False

    existing_packs = list(
        WordPack.objects.filter(word_set=job.word_set)
        .prefetch_related('items__word')
        .order_by('order')
    )

    if existing_packs:
        packed_word_ids = set()
        for pack in existing_packs:
            for item in pack.items.all():
                packed_word_ids.add(item.word_id)

        new_words = [w for w in words if w.id not in packed_word_ids]
        if not new_words:
            duration = time.time() - start
            _log_step(
                job, GenerationJobLog.Step.PACK_CREATION,
                GenerationJob.Status.COMPLETED,
                duration=duration,
                output_data={
                    'packs_created': 0,
                    'words_added_to_existing': 0,
                    'fallback_used': False,
                },
            )
            return existing_packs

        logger.info(
            "Existing packs missing %d generated words; regrouping all packs for graphic novel fit.",
            len(new_words),
        )
        regroup_existing_packs = True

    try:
        if not words_data:
            raise ValueError("No word definition data available for LLM pack grouping.")

        template = _llm_service.load_prompt_template('pack_grouping')

        max_per_pack = pack_size
        total_words = len(words)
        num_packs = math.ceil(total_words / max_per_pack)

        word_payload = [
            {
                'term': wd.get('term', ''),
                'part_of_speech': wd.get('part_of_speech', ''),
                'definition': wd.get('definition', ''),
                'example_sentence': wd.get('example_sentence', ''),
            }
            for wd in words_data or []
        ]
        input_json = json.dumps({
            'target_lexile': _content_lexile(job),
            'pack_count': num_packs,
            'max_words_per_pack': max_per_pack,
            'downstream_task': '5-page ESL graphic novel script generation',
            'grouping_goal': (
                'Create packs that can support story-engine routing, competing premises, '
                'a 5-page beat sheet, vocabulary plot roles, and a final graphic novel script.'
            ),
            'words': word_payload,
        }, ensure_ascii=False, indent=2)

        prompt_text = template.replace('{num_packs}', str(num_packs))
        prompt_text = prompt_text.replace('{max_per_pack}', str(max_per_pack))
        prompt_text = prompt_text.replace('{input_json}', input_json)
        user_prompt = ''
        result = _call_llm_with_config(site_config, prompt_text, user_prompt)
        llm_packs = result.get('packs', [])

        _validate_llm_pack_grouping(llm_packs, words, num_packs, max_per_pack)

        if regroup_existing_packs:
            WordPack.objects.filter(word_set=job.word_set).delete()

        packs = []
        for i, pack_data in enumerate(llm_packs):
            text_type = pack_data.get('text_type', 'fiction')
            if text_type not in ('fiction', 'narrative_nonfiction'):
                text_type = 'fiction'
            pack = WordPack.objects.create(
                word_set=job.word_set,
                label=pack_data.get('label', f'Pack {i + 1}'),
                text_type=text_type,
                order=i,
            )
            for idx, term in enumerate(pack_data.get('words', [])):
                word = word_map.get(term.lower())
                if word:
                    WordPackItem.objects.create(pack=pack, word=word, order=idx)
            packs.append(pack)

        logger.info("LLM grouped %d words into %d packs", len(words), len(packs))
        fallback_used = False
        fallback_reason = ''

    except Exception as llm_exc:
        if not allow_fallback:
            duration = time.time() - start
            _log_step(
                job, GenerationJobLog.Step.PACK_CREATION,
                GenerationJob.Status.FAILED,
                duration=duration,
                output_data=_log_metadata(
                    model=site_config['model'] if site_config else 'unknown',
                    prompt_template='pack_grouping',
                    prompt_text=locals().get('template', ''),
                    fallback_used=False,
                    quality_warning='Pack grouping failed before graphic novel generation.',
                ),
                error_message=str(llm_exc),
            )
            raise
        logger.warning("LLM pack grouping failed, falling back to sequential: %s", llm_exc)
        if regroup_existing_packs:
            WordPack.objects.filter(word_set=job.word_set).delete()
        packs = _fallback_create_sequential_packs(job, words, pack_size)
        fallback_used = True
        fallback_reason = str(llm_exc)

    duration = time.time() - start
    _log_step(
        job, GenerationJobLog.Step.PACK_CREATION,
        GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data=_log_metadata(
            model=site_config['model'] if site_config else 'unknown',
            prompt_template='pack_grouping',
            prompt_text=locals().get('template', ''),
            packs_created=len(packs),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            quality_warning=(
                'Sequential fallback pack grouping used; graphic novel quality may be lower.'
                if fallback_used else ''
            ),
        ),
    )

    return packs



def _step_generate_primers(job, words, words_data, site_config=None):
    """
    Step 6: Call LLM to generate primer card content for each word.
    Uses definition and example_sentence from step 1 (word lookup).
    LLM generates syllable_text and kid_friendly_definition only.
    """
    if site_config is None:
        from vocabulary.services.generation.llm_config_service import get_step_config
        site_config = get_step_config('primer_gen')['primary']
    start = time.time()
    try:
        template = _llm_service.load_prompt_template('primer_generation')

        word_info_parts = []
        words_data_map = {}
        for wd in words_data:
            term = wd['term']
            words_data_map[term.lower()] = wd
            word_info_parts.append(
                f"- {term} ({wd.get('part_of_speech', '')}): "
                f"definition: {wd.get('definition', '')} | "
                f"example: {wd.get('example_sentence', '')}"
            )

        user_prompt = '\n'.join(word_info_parts)
        prompt_text = template.replace('{target_lexile}', str(_content_lexile(job)))
        result = _call_llm_with_config(site_config, prompt_text, user_prompt)
        primers = result.get('primer_cards', [])

        word_map = {w.text.lower(): w for w in words}
        created_count = 0
        created_terms = set()

        for pc in primers:
            term = pc.get('term', '').lower()
            word = word_map.get(term)
            if not word:
                logger.warning("Primer for unknown term '%s', skipping", term)
                continue

            wd = words_data_map.get(term, {})
            example = wd.get('example_sentence', '')

            PrimerCardContent.objects.update_or_create(
                word=word,
                defaults={
                    'syllable_text': pc.get('syllable_text', ''),
                    'kid_friendly_definition': pc.get('kid_friendly_definition', ''),
                    'example_sentence': example,
                },
            )
            created_count += 1
            created_terms.add(term)

        missing_terms = set(word_map) - created_terms
        if missing_terms:
            raise ValueError(f"Primer generation missing target words: {sorted(missing_terms)}")

        job.primer_cards_created = created_count
        job.save(update_fields=['primer_cards_created'])

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.PRIMER_GEN,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data=_log_metadata(
                model=site_config['model'],
                prompt_template='primer_generation',
                prompt_text=template,
                primers_created=created_count,
                target_word_count=len(word_map),
            ),
        )

    except Exception as exc:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.PRIMER_GEN,
            GenerationJob.Status.FAILED,
            duration=duration,
            error_message=str(exc),
        )
        raise
