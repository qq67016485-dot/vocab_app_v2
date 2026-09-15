"""Graphic novel candidate selection + cloze promotion.

An admin generates several candidate novels per pack and picks one to publish.
Selecting a candidate is the single gate that makes a pack's graphic novel (and
its practice cloze) student-visible. This module owns that transition.
"""
import logging

from django.db import transaction

from vocabulary.models import ClozeItem, GraphicNovel
from vocabulary.services.generation.graphic_novel_script import (
    _candidate_novel_is_complete,
)

logger = logging.getLogger(__name__)


class IncompleteCandidateError(Exception):
    """Raised when an admin selects a candidate that is not fully generated."""


@transaction.atomic
def select_graphic_novel_candidate(novel_id):
    """Mark ``novel_id`` as the selected candidate for its pack and publish it.

    - Sets ``is_selected=True`` on this novel and ``False`` on its siblings.
    - Promotes this novel's staged cloze (``novel=<id>``) into the pack's active
      set: deletes the prior promoted rows (``novel=None``) and re-creates them
      from the selected candidate's cloze.

    Idempotent and reversible: re-selecting a different candidate flips the flags
    and re-promotes that candidate's cloze. Returns the selected ``GraphicNovel``.

    Raises ``IncompleteCandidateError`` when the candidate is not fully
    generated (the pipeline's ``_candidate_novel_is_complete`` notion: story
    pages + review page + staged cloze). Publishing an incomplete candidate
    would delete the pack's active cloze and promote nothing — silent data
    loss behind a 200.
    """
    novel = (
        GraphicNovel.objects.select_related('pack')
        .get(id=novel_id)
    )
    if not _candidate_novel_is_complete(novel):
        raise IncompleteCandidateError(
            f'Candidate {novel.candidate_index} is incomplete (missing story '
            'pages, review page, or staged cloze) and cannot be published. '
            'Regenerate it first.'
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
    """Replace the pack's active cloze (both FKs NULL) with the selected novel's.

    The active set is shared across content types, so this clears whatever was
    promoted last (a graphic novel or an infographic) and re-creates it from this
    novel's staged rows — last published wins, which is fine since cloze is
    medium-agnostic vocabulary practice.
    """
    ClozeItem.objects.filter(
        pack=pack, novel__isnull=True, infographic__isnull=True,
    ).delete()
    staged = ClozeItem.objects.filter(pack=pack, novel=novel).order_by('order')
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
        "Promoted %d cloze items for pack '%s' from novel %d",
        len(promoted), pack.label, novel.id,
    )
