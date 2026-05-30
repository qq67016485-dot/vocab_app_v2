"""Shared helpers for the graphic novel pipeline steps.

Contains formatting utilities, artifact I/O, substep execution, and small
pure functions shared by both the script generation and image generation
substeps. Validation logic lives in `graphic_novel_validators`.
"""
import json
import logging
import os
import time

from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify

from vocabulary.models import GenerationJob, GenerationJobLog
from vocabulary.services.canon_service import (
    LEXI_CHARACTERS,
    load_character_prompt_injection,
    load_vault_image_prompt,
)
from vocabulary.services.generation.constants import (
    GRAPHIC_NOVEL_ALLOWED_PAGE_COUNTS,
    GRAPHIC_NOVEL_DEFAULT_PAGE_COUNT,
    LEXI_LEGENDS_AGE_LEXILE_THRESHOLD,
)
from vocabulary.services.generation.helpers import (
    _call_llm_with_config,
    _log_metadata,
    _log_step,
)

logger = logging.getLogger(__name__)


CHAR_INK_COLORS = {
    'leo': ('cyan', '#16D9FF'),
    'amara': ('gold', '#F6C84C'),
    'mei': ('multicolor neon', '#FF3BD5'),
    'hugo': ('orange', '#FF8A2A'),
}


SECONDARY_CHARACTER_ANCHOR_TEMPLATE_PATH = os.path.join(
    settings.BASE_DIR, 'vocabulary', 'prompts', 'secondary_character_anchor.txt',
)

WORLD_CONTEXT_PATH = os.path.join(
    settings.BASE_DIR, 'vocabulary', 'prompts', 'graphic_novel_world_context.txt',
)


def _load_world_context():
    with open(WORLD_CONTEXT_PATH, 'r', encoding='utf-8') as f:
        return f.read().strip()


def _page_vocab_words(page_data):
    words = []
    for panel in page_data.get('panels', []):
        for word in panel.get('vocab_words', []):
            if word and word not in words:
                words.append(word)
    for word in page_data.get('vocab_words', []):
        if word and word not in words:
            words.append(word)
    return words


def _format_characters_for_image_prompt(characters):
    if not characters:
        return 'No character reference provided.'
    lines = []
    for char in characters:
        name = char.get('name', 'Unknown')
        desc = char.get('visual_description', '')
        lines.append(f"- {name}: {desc}")
    return '\n'.join(lines)


def _format_character_name_colors(page):
    if page.page_number != 1:
        return ''
    characters = page.characters_featured or []
    if not characters:
        return ''
    lines = []
    for name in characters:
        key = str(name).strip().lower()
        if key in CHAR_INK_COLORS:
            color_name, hex_code = CHAR_INK_COLORS[key]
            lines.append(
                f"When {name}'s name first appears (speech bubble, caption, or name label), "
                f"render it in their signature Ink color: {color_name} ({hex_code})."
            )
    if not lines:
        return ''
    lines.insert(0, "This is Page 1 — characters are being introduced.")
    return '\n'.join(lines)


def _characters_for_graphic_novel_page(page):
    featured_names = {
        str(name).strip().lower()
        for name in (page.characters_featured or [])
        if str(name).strip()
    }
    if not featured_names:
        return []
    age_band = page.novel.metadata.get('age_band', '9yo')
    anchors = (page.novel.metadata or {}).get('secondary_character_anchors', {})
    characters = []
    for name in featured_names:
        if name in LEXI_CHARACTERS:
            canon_injection = load_character_prompt_injection(name, age_band)
            if canon_injection:
                characters.append({'name': name.title(), 'visual_description': canon_injection})
                continue
        elif name in anchors:
            characters.append({'name': name.title(), 'visual_description': anchors[name]})
            continue
        for char in (page.novel.characters or []):
            if str(char.get('name', '')).strip().lower() == name:
                characters.append(char)
                break
    return characters


def _find_secondary_characters_needing_anchors(result: dict) -> list[str]:
    """Identify secondary characters with dialogue on non-consecutive pages."""
    pages = result.get('pages', [])
    if not pages:
        return []

    char_pages: dict[str, list[int]] = {}
    chars_with_dialogue: set[str] = set()

    for page_data in pages:
        page_num = page_data.get('page_number', 0)
        for name in page_data.get('characters_featured', []):
            key = str(name).strip().lower()
            if key and key not in LEXI_CHARACTERS:
                char_pages.setdefault(key, []).append(page_num)
        for panel in page_data.get('panels', []):
            for line in panel.get('dialogue', []):
                speaker = str(line.get('speaker', '')).strip().lower()
                if speaker and speaker not in LEXI_CHARACTERS:
                    chars_with_dialogue.add(speaker)

    needing_anchors = []
    for name, appearances in char_pages.items():
        if name not in chars_with_dialogue:
            continue
        sorted_pages = sorted(appearances)
        has_gap = any(
            sorted_pages[i + 1] - sorted_pages[i] > 1
            for i in range(len(sorted_pages) - 1)
        )
        if has_gap:
            needing_anchors.append(name)

    return needing_anchors


def _generate_secondary_character_anchors(
    result: dict, novel_metadata: dict, site_config: dict,
) -> dict[str, str]:
    """Generate visual anchor sheets for qualifying secondary characters."""
    names = _find_secondary_characters_needing_anchors(result)
    if not names:
        return {}

    try:
        with open(SECONDARY_CHARACTER_ANCHOR_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            system_template = f.read()
    except (FileNotFoundError, OSError):
        logger.warning("Secondary character anchor prompt template not found.")
        return {}

    char_lookup = {
        str(c.get('name', '')).strip().lower(): c
        for c in result.get('characters', [])
    }
    title = result.get('title', '')
    style_prompt = result.get('style_prompt', '')
    age_band = novel_metadata.get('age_band', '9yo')

    anchors: dict[str, str] = {}
    for name in names:
        char_data = char_lookup.get(name, {})
        char_desc = char_data.get('visual_description', '')
        if not char_desc:
            continue

        system_prompt = system_template.format(
            char_name=name.title(),
            char_desc=char_desc,
            title=title,
            style_prompt=style_prompt,
            age_band=age_band,
        )

        try:
            anchor_text = _call_llm_with_config(site_config, system_prompt, '')
            if anchor_text and len(anchor_text.strip()) > 20:
                anchors[name] = anchor_text.strip()
                logger.info(
                    "Generated visual anchor for secondary character '%s'.", name,
                )
        except Exception:
            logger.warning(
                "Failed to generate visual anchor for '%s'; using brief description.",
                name, exc_info=True,
            )

    return anchors


def _format_graphic_novel_setting_context(page):
    if page.is_review_page:
        return ''
    if page.is_vault_page:
        vault_zone = (page.vault_zone or '').strip().replace(' ', '-').replace('_', '-').lower()
        return load_vault_image_prompt(vault_zone)
    panels = page.panel_descriptions or []
    if not panels:
        return ''
    first_scene = panels[0].get('scene_description', '')
    setting_key = (page.setting_key or '').replace('_', ' ')
    if first_scene:
        return f"Setting: {setting_key}. {first_scene.split('.')[0]}."
    if setting_key:
        return f"Setting: {setting_key}."
    return ''


def _format_panels_as_prose(panels):
    lines = []
    for panel in panels:
        num = panel.get('panel_number', '')
        scene = panel.get('scene_description', '')
        narration = panel.get('narration', '')
        dialogue = panel.get('dialogue', [])
        highlight = panel.get('vocab_highlight_note', '')

        parts = [f"Panel {num}"]
        if scene:
            parts[0] += f": {scene}"
        if narration:
            parts.append(f'  Narration: "{narration}"')
        for line in dialogue:
            speaker = line.get('speaker', '')
            text = line.get('text', '')
            if speaker and text:
                parts.append(f'  {speaker}: "{text}"')
        if highlight:
            parts.append(f'  Vocab note: {highlight}')
        lines.append('\n'.join(parts))
    return '\n\n'.join(lines)


def _format_synopsis_for_page(page):
    if page.page_number <= 1:
        return page.novel.synopsis
    title = page.novel.title
    beat = ''
    for p in (page.novel.metadata or {}).get('beat_sheet', []):
        if p.get('page') == page.page_number:
            beat = p.get('why_this_page_matters', '')
            break
    if beat:
        return f"Story: {title}. This page: {beat[:200]}"
    return page.novel.synopsis


def _format_vocab_highlighting(page):
    vocab_words = page.vocab_words_used or []
    if not vocab_words:
        return ''
    characters = page.characters_featured or []
    active_inks = []
    for name in characters:
        key = str(name).strip().lower()
        if key in CHAR_INK_COLORS:
            color_name, hex_code = CHAR_INK_COLORS[key]
            active_inks.append(f"{name}'s {color_name} Ink ({hex_code})")
    words_str = ', '.join(vocab_words)
    lines = [f"Target vocabulary words on this page: {words_str}."]
    if active_inks:
        lines.append(
            f"When a vocabulary word appears through a character's Ink VFX, "
            f"render it in that character's Ink color: {'; '.join(active_inks)}."
        )
    lines.append(
        "Vocabulary words in narration captions or speech bubbles: render in "
        "bold bright orange (#FF8A2A) with a subtle luminous edge. "
        "All OTHER caption and narration text must be white or light cream — "
        "never gold, yellow, or warm tones that compete with the orange highlights. "
        "Must remain large and readable."
    )
    lines.append(
        "Ink VFX should be atmospheric character-colored glow around the word, "
        "not extra floating text."
    )
    return '\n'.join(lines)


def _format_vocab_details_for_review(page):
    from vocabulary.models import PrimerCardContent

    pack = page.novel.pack
    items = list(
        pack.items.select_related('word')
        .prefetch_related('word__primer_content', 'word__definitions')
        .all()
    )

    primer_defs = {}
    fallback_defs = {}
    for item in items:
        key = item.word.text.lower()
        try:
            primer_defs[key] = item.word.primer_content.kid_friendly_definition
        except PrimerCardContent.DoesNotExist:
            first_def = item.word.definitions.first()
            if first_def:
                fallback_defs[key] = ' '.join(first_def.definition_text.split()[:8])

    lines = []
    for word in page.vocab_words_used:
        definition = primer_defs.get(word.lower(), '') or fallback_defs.get(word.lower(), '')
        lines.append(f"- {word}: {definition}")
    return '\n'.join(lines) if lines else 'No vocabulary words provided.'


def _graphic_novel_artifact_dir(job, pack):
    pack_slug = slugify(pack.label) or f'pack-{pack.id}'
    return os.path.abspath(os.path.join(
        settings.BASE_DIR,
        '..',
        'temp',
        'generation_artifacts',
        f'job_{job.id}',
        f'pack_{pack.id}_{pack_slug}',
    ))


def _write_graphic_novel_artifact(job, pack, substep, filename, model, input_summary, response):
    artifact_dir = _graphic_novel_artifact_dir(job, pack)
    os.makedirs(artifact_dir, exist_ok=True)
    filepath = os.path.join(artifact_dir, filename)
    payload = {
        'job_id': job.id,
        'pack_id': pack.id,
        'pack_label': pack.label,
        'substep': substep,
        'model': model,
        'created_at': timezone.now().isoformat(),
        'input_summary': input_summary,
        'response': response,
    }
    with open(filepath, 'w', encoding='utf-8') as artifact_file:
        json.dump(payload, artifact_file, ensure_ascii=False, indent=2)
    return filepath


def _load_substep_artifact(job, pack, substep_config):
    """Load a previously saved substep artifact's response from disk."""
    artifact_dir = _graphic_novel_artifact_dir(job, pack)
    filepath = os.path.join(artifact_dir, substep_config['filename'])
    if not os.path.isfile(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        payload = json.load(f)
    return payload.get('response')


def _graphic_novel_word_summary(pack_words_data):
    return [
        {
            'term': wd.get('term', ''),
            'part_of_speech': wd.get('part_of_speech', ''),
            'definition': wd.get('definition', ''),
        }
        for wd in pack_words_data
    ]


def _graphic_novel_artifact_summary(substep, response):
    if substep == 'team_selection':
        return {
            'selected_away_team': response.get('selected_away_team', []),
            'vault_framing': response.get('vault_framing'),
        }
    if substep == 'router_premises':
        premises = response.get('premises', [])
        return {
            'narrative_approach': response.get('narrative_approach', ''),
            'premise_count': len(premises),
            'hard_to_integrate_words': response.get('hard_to_integrate_words', []),
        }
    if substep == 'premise_scoring':
        winner = response.get('winning_premise') or response.get('winner') or {}
        scores = response.get('scores') or response.get('scored_premises') or []
        return {
            'winning_premise_id': winner.get('id') or response.get('winning_premise_id'),
            'confidence': response.get('confidence') or winner.get('confidence'),
            'score_count': len(scores),
        }
    if substep == 'beat_sheet_vocab_roles':
        beat_sheet = response.get('beat_sheet', [])
        vocab_roles = response.get('vocab_roles', {})
        return {
            'page_count': len(beat_sheet),
            'vocab_role_count': len(vocab_roles),
        }
    pages = response.get('pages', [])
    cloze_items = response.get('cloze_items', [])
    return {
        'title': response.get('title', ''),
        'page_count': len(pages),
        'cloze_count': len(cloze_items),
    }


def _log_graphic_novel_substep(job, pack, substep, label, status, duration=None,
                               artifact_path='', summary=None, error_message='', model=None,
                               prompt_template=None, prompt_text=None):
    output_data = {
        'substep': substep,
        'substep_label': label,
        'pack_id': pack.id,
        'pack_label': pack.label,
    }
    output_data.update(_log_metadata(
        model=model,
        prompt_template=prompt_template,
        prompt_text=prompt_text,
    ))
    if artifact_path:
        output_data['artifact_path'] = artifact_path
        output_data['artifact_name'] = os.path.basename(artifact_path)
    if summary is not None:
        output_data['summary'] = summary

    return _log_step(
        job,
        GenerationJobLog.Step.GRAPHIC_NOVEL_SCRIPT,
        status,
        duration=duration,
        output_data=output_data,
        error_message=error_message,
    )


def _run_graphic_novel_substep(job, pack, substep_config, site_config, system_prompt,
                               user_prompt, input_summary, validator=None,
                               max_retries=1, prompt_template_name=None, ctx=None):
    substep = substep_config['key']
    label = substep_config['label']
    template_name = prompt_template_name or substep_config['template']
    last_exc = None

    world_context = _load_world_context()
    if '\n' in system_prompt:
        role_line, rest = system_prompt.split('\n', 1)
        system_prompt = f"{role_line}\n\n{world_context}\n{rest}"
    else:
        system_prompt = f"{system_prompt}\n\n{world_context}"

    for attempt in range(1 + max_retries):
        _log_graphic_novel_substep(
            job, pack, substep, label, GenerationJob.Status.RUNNING,
            summary={'message': f'{label} started (attempt {attempt + 1}).'},
            model=site_config['model'],
            prompt_template=template_name,
            prompt_text=system_prompt,
        )
        start = time.time()
        artifact_path = ''
        try:
            response = _call_llm_with_config(site_config, system_prompt, user_prompt)
            artifact_path = _write_graphic_novel_artifact(
                job,
                pack,
                substep,
                substep_config['filename'],
                site_config['model'],
                input_summary,
                response,
            )
            if validator:
                validator(response, ctx)
            duration = time.time() - start
            _log_graphic_novel_substep(
                job,
                pack,
                substep,
                label,
                GenerationJob.Status.COMPLETED,
                duration=duration,
                artifact_path=artifact_path,
                summary=_graphic_novel_artifact_summary(substep, response),
                model=site_config['model'],
                prompt_template=template_name,
                prompt_text=system_prompt,
            )
            return response, artifact_path
        except Exception as exc:
            last_exc = exc
            duration = time.time() - start
            _log_graphic_novel_substep(
                job,
                pack,
                substep,
                label,
                GenerationJob.Status.FAILED,
                duration=duration,
                artifact_path=artifact_path,
                summary={'message': f'{label} failed (attempt {attempt + 1}).'},
                error_message=str(exc),
                model=site_config['model'],
                prompt_template=template_name,
                prompt_text=system_prompt,
            )
            if attempt < max_retries:
                logger.warning(
                    "Substep %s for pack '%s' failed on attempt %d; retrying: %s",
                    substep, pack.label, attempt + 1, exc,
                )

    raise last_exc


def _format_graphic_novel_prompt(template, payload):
    return template.replace('{input_json}', json.dumps(payload, ensure_ascii=False, indent=2))


def _target_terms_from_input(input_summary):
    return {
        word.lower()
        for word in input_summary.get('words', [])
        if word
    }


def _lexi_legends_age_band(target_lexile):
    return '9yo' if target_lexile <= LEXI_LEGENDS_AGE_LEXILE_THRESHOLD else '12yo'


def _expected_page_count_from_summary(input_summary):
    winning_premise = (input_summary or {}).get('winning_premise') or {}
    page_count = winning_premise.get('page_count')
    if page_count in GRAPHIC_NOVEL_ALLOWED_PAGE_COUNTS:
        return page_count
    return GRAPHIC_NOVEL_DEFAULT_PAGE_COUNT


def _text_terms_from_graphic_novel_page(page_data):
    text_parts = []
    for panel in page_data.get('panels', []):
        text_parts.append(panel.get('narration') or '')
        for dialogue in panel.get('dialogue', []):
            text_parts.append(dialogue.get('text') or '')
    return ' '.join(text_parts).lower()


def _count_direct_ink_uses(items):
    return sum(1 for item in items if item.get('uses_direct_ink') is True)
