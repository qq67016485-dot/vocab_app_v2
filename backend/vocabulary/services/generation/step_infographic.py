"""Infographic generation (Steps 9A design + 9B image).

A neutral, single-page educational alternative to the graphic novel. Each pack
produces ``INFOGRAPHIC_CANDIDATE_COUNT`` independent candidates; an admin selects
one to publish (see ``infographic_selection_service``). The design substep emits
the structured poster layout, the cloze substep stages per-candidate cloze, and
the image substep renders one poster image per candidate.

Mirrors the graphic novel module's shape (per-candidate artifacts, COMPLETED-log
resume, continue-on-failure images) but is much lighter — no canon, no team
selection, no multi-page continuity.
"""
import json
import logging
import os
import re
import time

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify

from vocabulary.models import (
    ClozeItem, GenerationJob, GenerationJobLog, Infographic,
)
from vocabulary.services.generation.constants import (
    INFOGRAPHIC_CANDIDATE_COUNT,
    INFOGRAPHIC_SUBSTEPS,
)
from vocabulary.services.generation.graphic_novel_helpers import (
    _graphic_novel_word_summary,
)
from vocabulary.services.generation.graphic_novel_validators import (
    SubstepContext,
    _validate_graphic_novel_cloze_result,
    _validate_words_data_covers_pack,
)
from vocabulary.services.generation.helpers import (
    _call_llm_with_config,
    _call_openai_image_releasing_db,
    _content_lexile,
    _log_metadata,
    _log_step,
)
from vocabulary.services.generation.llm_config_service import get_step_config
from vocabulary.services.image_utils import png_to_jpeg_bytes
import vocabulary.services.llm_service as _llm_service

logger = logging.getLogger(__name__)

DEFAULT_INFOGRAPHIC_STYLE = (
    'Modern flat-vector illustration in an editorial-infographic style (Dribbble / '
    'Behance / NotebookLM / data-visualization explainer look): flat design with '
    'subtle soft shading and soft gradients, clean crisp outlines and smooth '
    'geometric curves, simplified but detailed objects, a vibrant cohesive color '
    'palette with clean flat lighting and confident editorial color blocking, clean '
    'geometric sans-serif lettering. Not a children\'s storybook or cartoon look.'
)


# ---------------------------------------------------------------------------
# Artifact I/O (per pack + candidate), mirroring the graphic novel layout.
# ---------------------------------------------------------------------------

def _infographic_artifact_dir(job, pack, candidate_index):
    pack_slug = slugify(pack.label) or f'pack-{pack.id}'
    return os.path.abspath(os.path.join(
        settings.BASE_DIR, '..', 'temp', 'generation_artifacts',
        f'job_{job.id}', f'pack_{pack.id}_{pack_slug}', f'infographic_cand_{candidate_index}',
    ))


def _write_infographic_artifact(job, pack, substep, filename, model,
                                input_summary, response, candidate_index):
    artifact_dir = _infographic_artifact_dir(job, pack, candidate_index)
    os.makedirs(artifact_dir, exist_ok=True)
    filepath = os.path.join(artifact_dir, filename)
    payload = {
        'job_id': job.id,
        'pack_id': pack.id,
        'pack_label': pack.label,
        'candidate_index': candidate_index,
        'substep': substep,
        'model': model,
        'created_at': timezone.now().isoformat(),
        'input_summary': input_summary,
        'response': response,
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return filepath


def _load_infographic_artifact(job, pack, substep_config, candidate_index):
    artifact_dir = _infographic_artifact_dir(job, pack, candidate_index)
    filepath = os.path.join(artifact_dir, substep_config['filename'])
    if not os.path.isfile(filepath):
        return None
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f).get('response')


# ---------------------------------------------------------------------------
# Substep logging + execution
# ---------------------------------------------------------------------------

def _log_infographic_substep(job, pack, substep, label, status, duration=None,
                             artifact_path='', summary=None, error_message='',
                             model=None, prompt_template=None, prompt_text=None,
                             candidate_index=0):
    output_data = {
        'substep': substep,
        'substep_label': label,
        'pack_id': pack.id,
        'pack_label': pack.label,
        'candidate_index': candidate_index,
    }
    output_data.update(_log_metadata(
        model=model, prompt_template=prompt_template, prompt_text=prompt_text,
    ))
    if artifact_path:
        output_data['artifact_path'] = artifact_path
        output_data['artifact_name'] = os.path.basename(artifact_path)
    if summary is not None:
        output_data['summary'] = summary
    return _log_step(
        job, GenerationJobLog.Step.INFOGRAPHIC_DESIGN, status,
        duration=duration, output_data=output_data, error_message=error_message,
    )


def _run_infographic_substep(job, pack, substep_config, site_config, system_prompt,
                             user_prompt, input_summary, validator=None,
                             max_retries=2, ctx=None, candidate_index=0):
    substep = substep_config['key']
    label = substep_config['label']
    template_name = substep_config['template']
    last_exc = None

    for attempt in range(1 + max_retries):
        _log_infographic_substep(
            job, pack, substep, label, GenerationJob.Status.RUNNING,
            summary={'message': f'{label} started (attempt {attempt + 1}).'},
            model=site_config['model'], prompt_template=template_name,
            prompt_text=system_prompt, candidate_index=candidate_index,
        )
        start = time.time()
        artifact_path = ''
        try:
            response = _call_llm_with_config(site_config, system_prompt, user_prompt)
            artifact_path = _write_infographic_artifact(
                job, pack, substep, substep_config['filename'],
                site_config['model'], input_summary, response, candidate_index,
            )
            if validator:
                validator(response, ctx)
            duration = time.time() - start
            _log_infographic_substep(
                job, pack, substep, label, GenerationJob.Status.COMPLETED,
                duration=duration, artifact_path=artifact_path,
                summary={'message': f'{label} completed.'},
                model=site_config['model'], prompt_template=template_name,
                prompt_text=system_prompt, candidate_index=candidate_index,
            )
            return response, artifact_path
        except Exception as exc:
            last_exc = exc
            duration = time.time() - start
            _log_infographic_substep(
                job, pack, substep, label, GenerationJob.Status.FAILED,
                duration=duration, artifact_path=artifact_path,
                summary={'message': f'{label} failed (attempt {attempt + 1}).'},
                error_message=str(exc), model=site_config['model'],
                prompt_template=template_name, prompt_text=system_prompt,
                candidate_index=candidate_index,
            )
            if attempt < max_retries:
                logger.warning(
                    "Infographic substep %s for pack '%s' cand %d failed on attempt %d; retrying: %s",
                    substep, pack.label, candidate_index, attempt + 1, exc,
                )

    raise last_exc


# ---------------------------------------------------------------------------
# Resume detection (mirrors the GN COMPLETED-log scheme)
# ---------------------------------------------------------------------------

def _completed_substep_keys(job, pack, candidate_index):
    return {
        log.output_data.get('substep')
        for log in job.logs.filter(
            step=GenerationJobLog.Step.INFOGRAPHIC_DESIGN,
            status=GenerationJob.Status.COMPLETED,
        )
        if isinstance(log.output_data, dict)
        and log.output_data.get('pack_id') == pack.id
        and log.output_data.get('candidate_index', 0) == candidate_index
        and log.output_data.get('substep')
    }


def _resume_substep_index(job, pack, candidate_index):
    completed = _completed_substep_keys(job, pack, candidate_index)
    for idx, substep in enumerate(INFOGRAPHIC_SUBSTEPS):
        if substep['key'] not in completed:
            return idx
    return len(INFOGRAPHIC_SUBSTEPS) - 1


def _candidate_infographic(pack, candidate_index):
    return pack.infographics.filter(candidate_index=candidate_index).first()


def _prior_artifacts_exist(job, pack, up_to_idx, candidate_index):
    for idx in range(up_to_idx):
        if _load_infographic_artifact(
            job, pack, INFOGRAPHIC_SUBSTEPS[idx], candidate_index
        ) is None:
            return False
    return True


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

# Generic subtitle tags that add no learning value (e.g. "Topic: A Vocabulary
# Guide"). When the design LLM still appends one despite the prompt, strip it.
_GENERIC_SUBTITLE_RE = re.compile(
    r"\s*[:—\-]\s*(a |an |the )?(vocab(ulary)?|word|spelling|reading)"
    r"( guide| list| lesson| words| journey| adventure)?\s*$",
    re.IGNORECASE,
)


def _clean_infographic_title(title):
    """Drop a trailing generic subtitle (e.g. ': A Vocabulary Guide').

    Only strips when something meaningful remains before the separator, so a
    title that is *only* a subtitle is left untouched.
    """
    title = (title or '').strip()
    cleaned = _GENERIC_SUBTITLE_RE.sub('', title).strip()
    return cleaned or title


def _persist_candidate_infographic(pack, candidate_index, design_result,
                                   content_lexile, cloze_result):
    """Create the candidate Infographic + its staged cloze rows."""
    entries = design_result.get('entries', [])
    content = {
        'big_idea': design_result.get('big_idea', ''),
        'layout_mode': design_result.get('layout_mode', '') or 'panorama',
        'visual_structure': design_result.get('visual_structure', ''),
        'scene_description': design_result.get('scene_description', ''),
        'color_palette': design_result.get('color_palette', ''),
        'scene_elements': design_result.get('scene_elements', []),
        'entries': entries,
        # Kept for backwards compat with earlier flashcard-style content.
        'theme': design_result.get('scene_description', '') or design_result.get('theme', ''),
        'layout_notes': design_result.get('visual_structure', '') or design_result.get('layout_notes', ''),
    }
    infographic = Infographic.objects.create(
        pack=pack,
        candidate_index=candidate_index,
        is_selected=False,
        title=_clean_infographic_title(
            design_result.get('title', f'{pack.label} Infographic')
        ),
        intro_text=design_result.get('intro_text', ''),
        content=content,
        style_prompt=design_result.get('style_prompt', DEFAULT_INFOGRAPHIC_STYLE),
        reading_level=design_result.get('reading_level', content_lexile),
        metadata={},
    )

    word_map = {
        item.word.text.lower(): item.word
        for item in pack.items.select_related('word').all()
    }
    for idx, ci in enumerate((cloze_result or {}).get('cloze_items', [])):
        word = word_map.get(ci.get('term', '').lower())
        if not word:
            continue
        ClozeItem.objects.create(
            pack=pack,
            infographic=infographic,
            word=word,
            sentence_text=ci.get('sentence_text', ''),
            correct_answer=ci.get('correct_answer', ''),
            distractors=ci.get('distractors', []),
            order=idx,
        )

    return infographic


# ---------------------------------------------------------------------------
# Generation engine (one candidate, from a substep to the end)
# ---------------------------------------------------------------------------

def restart_infographic_from_substep(job, pack_id, substep_key, words_data,
                                     candidate_index=0):
    """Generate one infographic candidate for a pack, running from ``substep_key``.

    Deletes this candidate's existing infographic first (cascading its staged
    cloze); the pack's promoted cloze and sibling candidates are untouched.
    """
    from vocabulary.models import WordPack

    substep_keys = [s['key'] for s in INFOGRAPHIC_SUBSTEPS]
    if substep_key not in substep_keys:
        raise ValueError(f"Invalid infographic substep key: {substep_key}. Valid: {substep_keys}")
    start_idx = substep_keys.index(substep_key)

    pack = WordPack.objects.prefetch_related('items__word').get(
        id=pack_id, word_set=job.word_set,
    )
    pack.infographics.filter(candidate_index=candidate_index).delete()

    pack_word_keys = {t.lower() for t in pack.items.values_list('word__text', flat=True)}
    pack_words_data = [
        wd for wd in words_data if wd.get('term', '').lower() in pack_word_keys
    ]
    _validate_words_data_covers_pack(pack, pack_words_data)

    content_lexile = _content_lexile(job)
    base_input = {
        'pack_label': pack.label,
        'text_type': pack.text_type,
        'target_lexile': content_lexile,
        'words': _graphic_novel_word_summary(pack_words_data),
    }
    input_summary = {
        'pack_label': pack.label,
        'target_lexile': content_lexile,
        'word_count': len(pack_words_data),
        'words': [wd.get('term', '') for wd in pack_words_data],
    }

    # Reconstruct prior substeps from artifacts when resuming.
    design_result = None
    if start_idx > 0:
        design_result = _load_infographic_artifact(
            job, pack, INFOGRAPHIC_SUBSTEPS[0], candidate_index,
        )
        if design_result is None:
            raise ValueError(
                f"Cannot restart infographic from '{substep_key}': missing design "
                f"artifact for candidate {candidate_index}. Run from 'design'."
            )

    if start_idx <= 0:
        design_template = _llm_service.load_prompt_template(INFOGRAPHIC_SUBSTEPS[0]['template'])
        design_result, _ = _run_infographic_substep(
            job, pack, INFOGRAPHIC_SUBSTEPS[0],
            get_step_config(INFOGRAPHIC_SUBSTEPS[0]['config_key'])['primary'],
            design_template,
            json.dumps(base_input, ensure_ascii=False, indent=2),
            input_summary,
            validator=_validate_infographic_design_result,
            ctx=SubstepContext.from_input_summary(input_summary),
            candidate_index=candidate_index,
        )

    cloze_template = _llm_service.load_prompt_template(INFOGRAPHIC_SUBSTEPS[1]['template'])
    cloze_input = {**base_input, 'infographic_design': design_result}
    cloze_result, _ = _run_infographic_substep(
        job, pack, INFOGRAPHIC_SUBSTEPS[1],
        get_step_config(INFOGRAPHIC_SUBSTEPS[1]['config_key'])['primary'],
        cloze_template,
        json.dumps(cloze_input, ensure_ascii=False, indent=2),
        input_summary,
        validator=_validate_graphic_novel_cloze_result,
        ctx=SubstepContext.from_input_summary(input_summary),
        candidate_index=candidate_index,
    )

    return _persist_candidate_infographic(
        pack, candidate_index, design_result, content_lexile, cloze_result,
    )


def _term_in_text(term, text):
    """True if a target word (or a short inflection of it) appears in text.

    Matches on the term's stem so plurals / -ed / -ing forms count, mirroring
    the tolerance the caption check uses.
    """
    term = (term or '').strip()
    if not term:
        return True
    stem = term.lower()[:max(4, len(term) - 2)]
    return stem in (text or '').lower()


def _validate_infographic_design_result(result, ctx=None):
    entries = result.get('entries')
    if not isinstance(entries, list) or not entries:
        raise ValueError("Infographic design must return a non-empty 'entries' list.")
    for idx, entry in enumerate(entries):
        if not entry.get('term'):
            raise ValueError(f"Infographic entry {idx} missing 'term'.")
        if not entry.get('kid_friendly_definition'):
            raise ValueError(f"Infographic entry {idx} missing 'kid_friendly_definition'.")
    if not result.get('title'):
        raise ValueError("Infographic design must return a 'title'.")

    # The poster must be one connected explanatory scene, not a flashcard grid:
    # require scene elements that describe the illustration and carry the vocab.
    scene_elements = result.get('scene_elements')
    if not isinstance(scene_elements, list) or not scene_elements:
        raise ValueError(
            "Infographic design must return a non-empty 'scene_elements' list "
            "(the connected parts of the single illustrated scene)."
        )
    for idx, el in enumerate(scene_elements):
        if not el.get('caption'):
            raise ValueError(f"Scene element {idx} missing 'caption'.")
        if not el.get('illustration'):
            raise ValueError(f"Scene element {idx} missing 'illustration'.")
        # The caption must USE the word in a sentence, not define it. Reject the
        # glossary format ("word: meaning" / "word — meaning") that produces
        # flashcard-looking posters.
        caption = el.get('caption', '')
        for term in (el.get('vocab_terms') or []):
            if not term:
                continue
            for sep in (f"{term}:", f"{term} :", f"{term} —", f"{term} -", f"{term}-"):
                if sep.lower() in caption.lower():
                    raise ValueError(
                        f"Scene element {idx} caption uses a definition format "
                        f"('{sep.strip()} …') for '{term}'. Captions must USE the word "
                        f"in a sentence, not define it."
                    )
            # The word (or its stem) must actually appear in the caption sentence.
            if not _term_in_text(term, caption):
                raise ValueError(
                    f"Scene element {idx} caption must use the word '{term}' in context; "
                    f"it does not appear in the caption."
                )
    if not result.get('scene_description'):
        raise ValueError("Infographic design must return a 'scene_description'.")

    # The intro hook must let students meet EVERY target word by reading it,
    # so require each word (or a short inflection) to appear in intro_text.
    intro_text = result.get('intro_text', '')
    if not intro_text:
        raise ValueError("Infographic design must return an 'intro_text' hook.")
    intro_terms = [e.get('term') for e in entries if e.get('term')]
    missing_in_intro = [
        term for term in intro_terms if not _term_in_text(term, intro_text)
    ]
    if missing_in_intro:
        raise ValueError(
            "intro_text must use every target word in context so students meet "
            f"them while reading; missing {sorted(missing_in_intro)}."
        )

    if ctx and ctx.target_terms:
        entry_terms = {(e.get('term') or '').lower() for e in entries}
        missing = ctx.target_terms - entry_terms
        if missing:
            raise ValueError(
                f"Infographic design must cover every target word; missing {sorted(missing)}."
            )
        # Every target word must also be anchored somewhere in the scene.
        scene_terms = {
            str(t).lower()
            for el in scene_elements
            for t in (el.get('vocab_terms') or [])
        }
        unanchored = ctx.target_terms - scene_terms
        if unanchored:
            raise ValueError(
                f"Every target word must appear in a scene element's vocab_terms; "
                f"missing {sorted(unanchored)}."
            )


# ---------------------------------------------------------------------------
# Step 9A: design + cloze for all pack candidates
# ---------------------------------------------------------------------------

def _step_infographic_design(job, packs, words_data):
    """Generate ``INFOGRAPHIC_CANDIDATE_COUNT`` candidate infographics per pack.

    Skips candidates already complete (an Infographic row exists); resumes
    incomplete ones from the first substep lacking a COMPLETED log.
    """
    start = time.time()
    try:
        if not packs:
            raise RuntimeError(
                f"No packs found for job {job.id}. PACK_CREATION must run first."
            )

        total = 0
        for pack in packs:
            for candidate_index in range(INFOGRAPHIC_CANDIDATE_COUNT):
                if _candidate_infographic(pack, candidate_index):
                    logger.info(
                        "Pack '%s' infographic candidate %d already exists, skipping",
                        pack.label, candidate_index,
                    )
                    continue

                resume_idx = _resume_substep_index(job, pack, candidate_index)
                if resume_idx > 0 and _prior_artifacts_exist(
                    job, pack, resume_idx, candidate_index
                ):
                    resume_key = INFOGRAPHIC_SUBSTEPS[resume_idx]['key']
                else:
                    resume_key = INFOGRAPHIC_SUBSTEPS[0]['key']

                restart_infographic_from_substep(
                    job, pack.id, resume_key, words_data,
                    candidate_index=candidate_index,
                )
                total += 1

        job.infographics_created = Infographic.objects.filter(pack__in=packs).count()
        job.save(update_fields=['infographics_created'])

        _log_step(
            job, GenerationJobLog.Step.INFOGRAPHIC_DESIGN,
            GenerationJob.Status.COMPLETED,
            duration=time.time() - start,
            output_data={
                'prompt_template': 'infographic_design_pipeline',
                'infographics_created': total,
            },
        )
    except Exception as exc:
        _log_step(
            job, GenerationJobLog.Step.INFOGRAPHIC_DESIGN,
            GenerationJob.Status.FAILED,
            duration=time.time() - start, error_message=str(exc),
        )
        raise


# ---------------------------------------------------------------------------
# Step 9B: render one image per candidate infographic
# ---------------------------------------------------------------------------

def _mark_vocab_terms(caption, terms):
    """Wrap each target term in the caption with **markers**, case-insensitively.

    Uses word-boundary matching so a term marks its own occurrences (and simple
    inflections) without splitting longer words, and never double-wraps a term
    that is already marked.
    """
    marked = caption
    for term in terms:
        term = (term or '').strip()
        if not term:
            continue
        # Match the term as a whole word, optionally followed by a short suffix
        # (plurals / -ed / -ing), and skip occurrences already wrapped in **.
        pattern = re.compile(
            rf"(?<!\*)\b({re.escape(term)}\w{{0,3}})\b(?!\*)",
            re.IGNORECASE,
        )
        marked = pattern.sub(r"**\1**", marked, count=1)
    return marked


def _all_target_terms(infographic):
    """Every target vocab word for this infographic, de-duplicated, in order."""
    content = infographic.content or {}
    seen = set()
    terms = []
    for el in content.get('scene_elements') or []:
        for term in el.get('vocab_terms') or []:
            key = (term or '').strip().lower()
            if key and key not in seen:
                seen.add(key)
                terms.append(term.strip())
    if not terms:
        for entry in content.get('entries', []):
            term = (entry.get('term') or '').strip()
            key = term.lower()
            if key and key not in seen:
                seen.add(key)
                terms.append(term)
    return terms


def _format_scene_elements(infographic):
    """Render scene elements as a numbered, connected list for the image prompt."""
    content = infographic.content or {}
    elements = content.get('scene_elements') or []
    if not elements:
        # Backwards-compat fallback: synthesize elements from per-word entries.
        lines = []
        for entry in content.get('entries', []):
            term = entry.get('term', '')
            definition = entry.get('kid_friendly_definition', '')
            visual = entry.get('visual_idea', '')
            lines.append(
                f"- {visual or term}. Caption mentions **{term}**: {definition}."
            )
        return '\n'.join(lines) if lines else 'No scene elements provided.'

    lines = []
    for idx, el in enumerate(elements, 1):
        label = el.get('label', '')
        caption = el.get('caption', '')
        illustration = el.get('illustration', '')
        terms = el.get('vocab_terms') or []
        marked = _mark_vocab_terms(caption, terms)
        lines.append(
            f"{idx}. {label}: draw {illustration} "
            f"Caption (render the **word** in bold accent color): \"{marked}\""
        )
    return '\n'.join(lines)


_PANORAMA_GUIDANCE = (
    "Lay out these scene elements IN ORDER as ONE continuous landscape/scene, "
    "linked by a clearly drawn VISUAL SPINE (the winding road / river / trail / "
    "arrows / timeline from the scene description) that physically joins each "
    "element to the next so the reader's eye is pulled from the first element to "
    "the last. Element 1 is where the eye starts; the final element is where the "
    "path ends. Draw each element's illustrated detail integrated into the single "
    "landscape (not in a box), with its label and caption floating nearby on a "
    "callout line:"
)
_GALLERY_GUIDANCE = (
    "Arrange these scene elements as separate little illustrated scenes held "
    "together by ONE creative FRAMING DEVICE (the scrapbook / corkboard / shelf / "
    "desk / control panel from the scene description) — never a plain grid. Each "
    "element is its own small vignette tucked into the framing device, with its "
    "label and caption nearby on a callout line. Keep the framing device and a "
    "consistent style so the whole page feels like one designed piece:"
)


def build_infographic_image_prompt(infographic):
    """Build the OpenAI image prompt for one infographic. Shared by pipeline + redraw."""
    template = _llm_service.load_prompt_template('infographic_image')
    content = infographic.content or {}
    layout_mode = (content.get('layout_mode') or 'panorama').lower()
    layout_guidance = _GALLERY_GUIDANCE if layout_mode == 'gallery' else _PANORAMA_GUIDANCE
    target_terms = _all_target_terms(infographic)
    vocab_words = ', '.join(target_terms) if target_terms else '(the marked **words**)'
    return template.format(
        title=infographic.title,
        big_idea=content.get('big_idea', '') or infographic.intro_text,
        visual_structure=content.get('visual_structure', '') or 'labeled_scene',
        scene_description=content.get('scene_description', '') or content.get('theme', ''),
        color_palette=content.get('color_palette', ''),
        style_prompt=infographic.style_prompt or DEFAULT_INFOGRAPHIC_STYLE,
        layout_guidance=layout_guidance,
        scene_elements=_format_scene_elements(infographic),
        vocab_words=vocab_words,
    )


def _save_infographic_jpeg(infographic, image_bytes, filename):
    try:
        jpeg_bytes = png_to_jpeg_bytes(image_bytes)
    except ValueError as exc:
        logger.warning("Infographic JPEG conversion failed for %s: %s", filename, exc)
        return False
    infographic.image_jpeg.save(filename, ContentFile(jpeg_bytes), save=False)
    return True


def _step_infographic_image(job, packs):
    """Render one poster image per candidate infographic. Continue on failure."""
    _log_step(
        job, GenerationJobLog.Step.INFOGRAPHIC_IMAGE, GenerationJob.Status.RUNNING,
        output_data={'message': 'Starting infographic image generation'},
    )
    start = time.time()
    created = 0
    skipped = 0
    failed = []

    infographics = list(
        Infographic.objects.filter(pack__in=packs)
        .select_related('pack').order_by('pack_id', 'candidate_index')
    )
    if not infographics:
        logger.warning(
            "No infographics found for job %s image generation (%d packs).",
            job.id, len(packs),
        )
        _log_step(
            job, GenerationJobLog.Step.INFOGRAPHIC_IMAGE, GenerationJob.Status.FAILED,
            output_data={'images_created': 0, 'images_skipped': 0, 'failed': []},
            error_message="No infographics found for image generation.",
        )
        raise RuntimeError("No infographics found for image generation.")

    for ig in infographics:
        if ig.image:
            skipped += 1
            if ig.generation_status != Infographic.GenerationStatus.COMPLETED:
                ig.generation_status = Infographic.GenerationStatus.COMPLETED
                ig.generation_completed_at = ig.generation_completed_at or timezone.now()
                ig.save(update_fields=['generation_status', 'generation_completed_at'])
            continue

        label = f"{ig.pack.label} infographic cand {ig.candidate_index}"
        prompt = build_infographic_image_prompt(ig)
        slug = (slugify(ig.title) or 'infographic')[:60]

        ig.generation_status = Infographic.GenerationStatus.RUNNING
        ig.generation_attempts = (ig.generation_attempts or 0) + 1
        ig.generation_error = ''
        ig.generation_started_at = timezone.now()
        ig.generation_completed_at = None
        ig.save(update_fields=[
            'generation_status', 'generation_attempts', 'generation_error',
            'generation_started_at', 'generation_completed_at',
        ])

        try:
            logger.info("Generating infographic image for %s", label)
            image_bytes = _call_openai_image_releasing_db(prompt, size="1792x1024")
            filename = f"{slug}_cand_{ig.candidate_index}.png"
            ig.image.save(filename, ContentFile(image_bytes), save=False)
            jpeg_saved = _save_infographic_jpeg(
                ig, image_bytes, f"{slug}_cand_{ig.candidate_index}.jpg",
            )
            ig.prompt_used = prompt
            ig.generation_status = Infographic.GenerationStatus.COMPLETED
            ig.generation_error = ''
            ig.generation_completed_at = timezone.now()
            ig.save(update_fields=[
                'image', 'prompt_used', 'generation_status',
                'generation_error', 'generation_completed_at',
            ] + (['image_jpeg'] if jpeg_saved else []))
            created += 1
        except Exception as exc:
            logger.warning("Infographic image failed for %s: %s", label, exc)
            ig.generation_status = Infographic.GenerationStatus.FAILED
            ig.generation_error = str(exc)
            ig.generation_completed_at = timezone.now()
            ig.save(update_fields=[
                'generation_status', 'generation_error', 'generation_completed_at',
            ])
            failed.append(label)

    duration = time.time() - start
    if failed:
        _log_step(
            job, GenerationJobLog.Step.INFOGRAPHIC_IMAGE, GenerationJob.Status.FAILED,
            duration=duration,
            output_data={'images_created': created, 'images_skipped': skipped, 'failed': failed},
            error_message=f"{len(failed)} infographic image generation(s) failed.",
        )
        raise RuntimeError(f"Infographic image generation failed for {len(failed)} candidate(s).")

    _log_step(
        job, GenerationJobLog.Step.INFOGRAPHIC_IMAGE, GenerationJob.Status.COMPLETED,
        duration=duration,
        output_data={'images_created': created, 'images_skipped': skipped, 'failed': failed},
    )
    logger.info(
        "Infographic image generation completed for job %s: %d created, %d failed",
        job.id, created, len(failed),
    )
