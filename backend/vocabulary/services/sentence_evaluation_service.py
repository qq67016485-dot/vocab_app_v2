"""Answer-time judge for productive sentence-writing questions.

A student writes an original sentence using a target word; this service asks an
LLM to judge whether the word is used correctly and, on a miss, returns a
coaching hint (never the answer). See
docs/feature_plan/design-sentence-writing-questions.md.

Design points enforced here:
- Structured verdict only (verdict / error_type / hint) — the student's sentence
  is treated as untrusted data, never as instructions (prompt-injection floor).
- A small circuit breaker: repeated judge failures flip a short-lived cache flag
  so the practice picker can *exclude* sentence-write questions while the judge
  is unhealthy (students still get receptive questions). The flag clears on TTL.
- The judge is routed through the LLM config matrix (`sentence_judge` step key),
  so it is admin-tunable like every other step.
"""
import json
import logging

from django.core.cache import cache

from vocabulary.models import Question
import vocabulary.services.llm_service as _llm_service
from vocabulary.services.generation.helpers import _call_llm_with_config
from vocabulary.services.generation.llm_config_service import (
    get_step_config, LLMConfigError,
)

logger = logging.getLogger(__name__)

JUDGE_STEP_KEY = 'sentence_judge'
JUDGE_TEMPLATE = 'sentence_judge'

VALID_VERDICTS = ('correct', 'almost', 'incorrect')
VALID_ERROR_TYPES = (
    'none', 'wrong_meaning', 'wrong_form', 'spelling', 'echo_definition',
    'off_scenario',
)

SENTENCE_WRITE_TYPES = (
    Question.QuestionType.SENTENCE_WRITE_GUIDED,
    Question.QuestionType.SENTENCE_WRITE_OPEN,
)

# Circuit breaker: N consecutive failures within the window marks the judge
# unhealthy for UNHEALTHY_TTL seconds.
_FAIL_COUNT_KEY = 'sentence_judge:consecutive_failures'
_UNHEALTHY_KEY = 'sentence_judge:unhealthy'
_FAIL_THRESHOLD = 3
_UNHEALTHY_TTL = 300  # 5 min
_FAIL_COUNT_TTL = 120


class SentenceJudgeUnavailable(Exception):
    """Raised when the judge LLM cannot be reached / returns unusably."""


def is_judge_healthy() -> bool:
    """Whether the judge is currently considered healthy (breaker not tripped)."""
    return not cache.get(_UNHEALTHY_KEY, False)


def is_sentence_write_type(question_type) -> bool:
    return question_type in SENTENCE_WRITE_TYPES


def _record_failure() -> None:
    try:
        count = cache.get(_FAIL_COUNT_KEY, 0) + 1
        cache.set(_FAIL_COUNT_KEY, count, _FAIL_COUNT_TTL)
        if count >= _FAIL_THRESHOLD:
            cache.set(_UNHEALTHY_KEY, True, _UNHEALTHY_TTL)
            logger.warning(
                "Sentence judge marked unhealthy after %d consecutive failures.",
                count,
            )
    except Exception:  # cache must never break the request path
        logger.exception("Failed to record sentence-judge failure")


def _record_success() -> None:
    try:
        cache.delete(_FAIL_COUNT_KEY)
        cache.delete(_UNHEALTHY_KEY)
    except Exception:
        logger.exception("Failed to clear sentence-judge health flags")


def _clamp_str(value, limit=2000) -> str:
    if not isinstance(value, str):
        value = str(value or '')
    return value[:limit]


def evaluate_sentence(question, student_sentence, prior_attempts=None):
    """Judge one sentence attempt.

    Args:
        question: the Question (a sentence-write type).
        student_sentence: the child's raw sentence (untrusted).
        prior_attempts: list of {sentence, hint} from earlier tries this turn.

    Returns a dict:
        {
            'verdict': 'correct'|'almost'|'incorrect',
            'error_type': one of VALID_ERROR_TYPES,
            'hints': [str, ...],         # 1–3 short coaching bullets
            'hint': str,                 # bullets joined (back-compat / TTS)
            'is_correct': bool,          # verdict == 'correct'
        }

    Raises SentenceJudgeUnavailable if the judge cannot be used; the caller
    decides how to degrade (skip / discard).
    """
    options = question.options if isinstance(question.options, dict) else {}
    payload = {
        'term': question.word.text,
        'intended_sense': options.get('intended_sense', ''),
        'acceptable_use_notes': options.get('acceptable_use_notes', []),
        'scenario': question.question_text,
        'student_sentence': _clamp_str(student_sentence),
        'prior_attempts': [
            {
                'sentence': _clamp_str(a.get('sentence', '')),
                'hint': _clamp_str(a.get('hint', ''), 500),
            }
            for a in (prior_attempts or [])
        ][:5],
    }

    try:
        config = get_step_config(JUDGE_STEP_KEY)['primary']
    except LLMConfigError as exc:
        # A config error is at least as persistent as a network error — it must
        # also count toward the breaker, or the picker keeps serving sentence
        # questions that can never be judged.
        _record_failure()
        raise SentenceJudgeUnavailable(str(exc)) from exc

    try:
        template = _llm_service.load_prompt_template(JUDGE_TEMPLATE)
        result = _call_llm_with_config(config, template, json.dumps(payload))
    except Exception as exc:
        _record_failure()
        raise SentenceJudgeUnavailable(str(exc)) from exc

    if not isinstance(result, dict) or 'verdict' not in result:
        _record_failure()
        raise SentenceJudgeUnavailable("Judge returned an unexpected shape.")

    _record_success()
    return _normalize_verdict(result)


def _normalize_verdict(result: dict) -> dict:
    verdict = str(result.get('verdict', '')).strip().lower()
    if verdict not in VALID_VERDICTS:
        verdict = 'incorrect'

    error_type = str(result.get('error_type', '')).strip().lower()
    if error_type not in VALID_ERROR_TYPES:
        error_type = 'none' if verdict == 'correct' else 'wrong_meaning'

    # Coaching is a list of 1–3 short bullets. Accept the new `hints` array;
    # fall back to a legacy single `hint` string. Clamp each bullet, drop
    # blanks, and hard-cap at 3 (the schema cap is enforced here too, not just
    # in the prompt). `hint` (joined) is retained for storage/TTS back-compat.
    raw_hints = result.get('hints')
    if isinstance(raw_hints, list):
        hints = [_clamp_str(h, 300) for h in raw_hints if str(h or '').strip()][:3]
    else:
        single = _clamp_str(result.get('hint', ''), 500)
        hints = [single] if single else []

    return {
        'verdict': verdict,
        'error_type': error_type,
        'hints': hints,
        'hint': ' '.join(hints),
        'is_correct': verdict == 'correct',
    }
