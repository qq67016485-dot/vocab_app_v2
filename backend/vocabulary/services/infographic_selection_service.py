"""Infographic candidate selection + cloze promotion.

Mirrors ``graphic_novel_selection_service``: an admin generates several candidate
infographics per pack and picks one to publish. Selecting a candidate makes it
student-visible and promotes its staged cloze into the pack's active set.
"""
import logging

from django.db import transaction

from vocabulary.models import ClozeItem, Infographic

logger = logging.getLogger(__name__)


@transaction.atomic
def select_infographic_candidate(infographic_id):
    """Mark ``infographic_id`` as the selected candidate for its pack and publish it.

    - Sets ``is_selected=True`` on this infographic and ``False`` on its siblings.
    - Promotes this infographic's staged cloze (``infographic=<id>``) into the
      pack's active set (both FKs NULL), deleting the prior active rows first.

    Idempotent and reversible. Returns the selected ``Infographic``.
    """
    infographic = (
        Infographic.objects.select_related('pack').get(id=infographic_id)
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
