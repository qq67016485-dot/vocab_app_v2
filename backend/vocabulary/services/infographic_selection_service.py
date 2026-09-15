"""Infographic candidate selection + cloze promotion.

Mirrors ``graphic_novel_selection_service``: an admin generates several candidate
infographics per pack and picks one to publish. Selecting a candidate makes it
student-visible and promotes its staged cloze into the pack's active set.
"""
import logging

from django.db import transaction

from vocabulary.models import ClozeItem, Infographic

logger = logging.getLogger(__name__)


class IncompleteCandidateError(Exception):
    """Raised when an admin selects a candidate that is not fully generated."""


def _candidate_infographic_is_complete(infographic):
    """True when the candidate is publishable: rendered poster + staged cloze.

    The pipeline treats an Infographic row with staged cloze as done; for
    publishing, the candidate must also have its poster image — the one piece
    of content a student actually sees. ``display_image`` respects the
    original/edited variant pick.
    """
    return bool(infographic.display_image) and infographic.cloze_items.exists()


@transaction.atomic
def select_infographic_candidate(infographic_id):
    """Mark ``infographic_id`` as the selected candidate for its pack and publish it.

    - Sets ``is_selected=True`` on this infographic and ``False`` on its siblings.
    - Promotes this infographic's staged cloze (``infographic=<id>``) into the
      pack's active set (both FKs NULL), deleting the prior active rows first.

    Idempotent and reversible. Returns the selected ``Infographic``.

    Raises ``IncompleteCandidateError`` when the candidate has no rendered
    poster image or no staged cloze — publishing one would delete the pack's
    active cloze and promote nothing (silent data loss behind a 200).
    """
    infographic = (
        Infographic.objects.select_related('pack').get(id=infographic_id)
    )
    if not _candidate_infographic_is_complete(infographic):
        raise IncompleteCandidateError(
            f'Candidate {infographic.candidate_index} is incomplete (missing '
            'poster image or staged cloze) and cannot be published. '
            'Regenerate it first.'
        )
    pack = infographic.pack

    siblings = Infographic.objects.filter(pack=pack)
    siblings.exclude(id=infographic.id).filter(is_selected=True).update(is_selected=False)
    if not infographic.is_selected:
        infographic.is_selected = True
        infographic.save(update_fields=['is_selected'])

    _promote_cloze(pack, infographic)

    logger.info(
        "Selected infographic candidate %d (id %d) for pack '%s'",
        infographic.candidate_index, infographic.id, pack.label,
    )
    return infographic


def _promote_cloze(pack, infographic):
    """Replace the pack's active cloze (both FKs NULL) with this infographic's.

    The active set is shared across content types, so this clears whatever was
    promoted last (a graphic novel or an infographic) and re-creates it from this
    infographic's staged rows — last published wins (cloze is medium-agnostic).
    """
    ClozeItem.objects.filter(
        pack=pack, novel__isnull=True, infographic__isnull=True,
    ).delete()
    staged = ClozeItem.objects.filter(pack=pack, infographic=infographic).order_by('order')
    promoted = [
        ClozeItem(
            pack=pack,
            novel=None,
            infographic=None,
            word=ci.word,
            sentence_text=ci.sentence_text,
            correct_answer=ci.correct_answer,
            distractors=ci.distractors,
            order=ci.order,
        )
        for ci in staged
    ]
    ClozeItem.objects.bulk_create(promoted)
    logger.info(
        "Promoted %d cloze items for pack '%s' from infographic %d",
        len(promoted), pack.label, infographic.id,
    )
