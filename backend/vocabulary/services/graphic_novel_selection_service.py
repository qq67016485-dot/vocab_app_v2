"""Graphic novel candidate selection + cloze promotion.

An admin generates several candidate novels per pack and picks one to publish.
Selecting a candidate is the single gate that makes a pack's graphic novel (and
its practice cloze) student-visible. This module owns that transition.
"""
import logging

from django.db import transaction

from vocabulary.models import ClozeItem, GraphicNovel

logger = logging.getLogger(__name__)


@transaction.atomic
def select_graphic_novel_candidate(novel_id):
    """Mark ``novel_id`` as the selected candidate for its pack and publish it.

    - Sets ``is_selected=True`` on this novel and ``False`` on its siblings.
    - Promotes this novel's staged cloze (``novel=<id>``) into the pack's active
      set: deletes the prior promoted rows (``novel=None``) and re-creates them
      from the selected candidate's cloze.

    Idempotent and reversible: re-selecting a different candidate flips the flags
    and re-promotes that candidate's cloze. Returns the selected ``GraphicNovel``.
    """
    novel = (
        GraphicNovel.objects.select_related('pack')
        .get(id=novel_id)
    )
    pack = novel.pack

    # Flip selection flags for the whole pack in one pass.
    siblings = GraphicNovel.objects.filter(pack=pack)
    siblings.exclude(id=novel.id).filter(is_selected=True).update(is_selected=False)
    if not novel.is_selected:
        novel.is_selected = True
        novel.save(update_fields=['is_selected'])

    _promote_cloze(pack, novel)

    logger.info(
        "Selected graphic novel candidate %d (novel %d) for pack '%s'",
        novel.candidate_index, novel.id, pack.label,
    )
    return novel


def _promote_cloze(pack, novel):
    """Replace the pack's promoted cloze (novel=None) with the selected novel's."""
    ClozeItem.objects.filter(pack=pack, novel__isnull=True).delete()
    staged = ClozeItem.objects.filter(pack=pack, novel=novel).order_by('order')
    promoted = [
        ClozeItem(
            pack=pack,
            novel=None,
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
        "Promoted %d cloze items for pack '%s' from novel %d",
        len(promoted), pack.label, novel.id,
    )
