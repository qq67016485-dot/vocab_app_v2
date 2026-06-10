"""Tests for graphic novel candidate selection + cloze promotion."""
import pytest

from vocabulary.models import ClozeItem, GraphicNovel
from vocabulary.services.graphic_novel_selection_service import (
    select_graphic_novel_candidate,
)
from tests.factories import (
    GraphicNovelFactory, WordPackFactory, WordFactory, WordPackItemFactory,
)


@pytest.mark.django_db
class TestSelectGraphicNovelCandidate:
    def _make_candidate(self, pack, idx, word, *, selected=False):
        novel = GraphicNovelFactory(
            pack=pack, candidate_index=idx, is_selected=selected,
            title=f'Candidate {idx}',
        )
        ClozeItem.objects.create(
            pack=pack, novel=novel, word=word,
            sentence_text=f'The ____ thing happened in story {idx}.',
            correct_answer=word.text, distractors=['a', 'b'], order=0,
        )
        return novel

    def test_selects_candidate_and_clears_siblings(self):
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        c0 = self._make_candidate(pack, 0, word)
        c1 = self._make_candidate(pack, 1, word)
        c2 = self._make_candidate(pack, 2, word)

        select_graphic_novel_candidate(c1.id)

        c0.refresh_from_db(); c1.refresh_from_db(); c2.refresh_from_db()
        assert c1.is_selected is True
        assert c0.is_selected is False
        assert c2.is_selected is False

    def test_promotes_selected_candidate_cloze(self):
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        self._make_candidate(pack, 0, word)
        c1 = self._make_candidate(pack, 1, word)

        select_graphic_novel_candidate(c1.id)

        promoted = ClozeItem.objects.filter(pack=pack, novel__isnull=True)
        assert promoted.count() == 1
        assert promoted.first().sentence_text == 'The ____ thing happened in story 1.'
        # Staged candidate cloze is left intact.
        assert ClozeItem.objects.filter(pack=pack, novel=c1).count() == 1

    def test_reselect_replaces_promoted_cloze(self):
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        c0 = self._make_candidate(pack, 0, word)
        c1 = self._make_candidate(pack, 1, word)

        select_graphic_novel_candidate(c0.id)
        select_graphic_novel_candidate(c1.id)

        promoted = ClozeItem.objects.filter(pack=pack, novel__isnull=True)
        assert promoted.count() == 1
        assert promoted.first().sentence_text == 'The ____ thing happened in story 1.'
        c0.refresh_from_db()
        assert c0.is_selected is False

    def test_idempotent_reselect_same_candidate(self):
        pack = WordPackFactory()
        word = WordFactory(text='bright')
        WordPackItemFactory(pack=pack, word=word, order=0)
        c0 = self._make_candidate(pack, 0, word)

        select_graphic_novel_candidate(c0.id)
        select_graphic_novel_candidate(c0.id)

        assert ClozeItem.objects.filter(pack=pack, novel__isnull=True).count() == 1
        c0.refresh_from_db()
        assert c0.is_selected is True
