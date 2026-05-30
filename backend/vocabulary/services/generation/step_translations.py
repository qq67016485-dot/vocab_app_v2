"""Pipeline step 3: Generate Translations."""
import logging
import time

from django.contrib.contenttypes.models import ContentType

from vocabulary.models import (
    WordDefinition, Translation,
    GenerationJob, GenerationJobLog,
)
from vocabulary.services.generation.helpers import (
    _log_step, _log_metadata, _call_llm_with_config,
)
import vocabulary.services.llm_service as _llm_service

logger = logging.getLogger(__name__)


def _step_generate_translations(job, words, words_data, site_config=None):
    """Step 3: Call LLM to generate translations for definitions and examples."""
    if site_config is None:
        from vocabulary.services.generation.llm_config_service import get_step_config
        site_config = get_step_config('translation')['primary']
    start = time.time()
    try:
        template = _llm_service.load_prompt_template('translation')
        target_language = job.target_language

        items_list = []
        for wd in words_data:
            term = wd.get('term', '')
            items_list.append(f"- term: {term}")
            items_list.append(f"  definition_text: {wd.get('definition', '')}")
            example = wd.get('example_sentence', '')
            if example:
                items_list.append(f"  example_sentence: {example}")

        items_str = '\n'.join(items_list)
        prompt = template.format(
            target_language=target_language,
            items_to_translate=items_str,
        )

        result = _call_llm_with_config(site_config, prompt, f"Translate to {target_language}")
        translations = result.get('translations', [])

        wd_ct = ContentType.objects.get_for_model(WordDefinition)

        word_map_lower = {w.text.lower(): w for w in words}
        expected_terms = set()
        for wd in words_data:
            term = (wd.get('term') or '').lower()
            if term and term in word_map_lower:
                expected_terms.add(term)
        matched_terms_fields: set[tuple[str, str]] = set()

        for trans in translations:
            term = (trans.get('term') or '').lower()
            field_name = trans.get('source_field', '')
            translated_text = trans.get('translated_text', '')

            if not term or not field_name or not translated_text:
                continue

            word = word_map_lower.get(term)
            if not word:
                logger.warning("Translation returned unknown term: %s", term)
                continue

            defn = word.definitions.first()
            if not defn:
                continue

            if field_name in ('definition_text', 'example_sentence'):
                Translation.objects.update_or_create(
                    content_type=wd_ct,
                    object_id=defn.id,
                    field_name=field_name,
                    language=target_language,
                    defaults={'translated_text': translated_text},
                )
                matched_terms_fields.add((term, field_name))

        missing_terms = expected_terms - {t for t, _ in matched_terms_fields}
        if missing_terms:
            raise ValueError(f"Translation response missing terms: {sorted(missing_terms)}")

        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.TRANSLATION,
            GenerationJob.Status.COMPLETED,
            duration=duration,
            output_data=_log_metadata(
                model=site_config['model'],
                prompt_template='translation',
                prompt_text=template,
                translations_count=len(translations),
                expected_terms=len(expected_terms),
            ),
        )

    except Exception as exc:
        duration = time.time() - start
        _log_step(
            job, GenerationJobLog.Step.TRANSLATION,
            GenerationJob.Status.FAILED,
            duration=duration,
            error_message=str(exc),
        )
        raise
