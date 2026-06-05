"""Tests for student-facing JPEG companion images."""
import io

import pytest
from django.core.files.base import ContentFile
from PIL import Image

from vocabulary.models import GraphicNovel, GraphicNovelPage, WordPack
from vocabulary.services.image_utils import png_to_jpeg_bytes
from vocabulary.services.generation.graphic_novel_images import (
    backfill_page_jpegs, _step_graphic_novel_images,
)
from tests.factories import GenerationJobFactory, GraphicNovelPageFactory


def _png_bytes(mode='RGBA', size=(8, 8), color=(255, 0, 0, 128)):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format='PNG')
    return buf.getvalue()


class TestPngToJpegBytes:
    def test_converts_rgba_to_jpeg(self):
        jpeg = png_to_jpeg_bytes(_png_bytes(mode='RGBA'))
        with Image.open(io.BytesIO(jpeg)) as img:
            assert img.format == 'JPEG'
            assert img.mode == 'RGB'  # alpha flattened away

    def test_converts_rgb_passthrough(self):
        jpeg = png_to_jpeg_bytes(_png_bytes(mode='RGB', color=(0, 128, 0)))
        with Image.open(io.BytesIO(jpeg)) as img:
            assert img.format == 'JPEG'
            assert img.mode == 'RGB'

    def test_jpeg_is_smaller_than_png_for_high_entropy_input(self):
        # Random noise is incompressible for lossless PNG; lossy JPEG wins.
        import random
        rng = random.Random(42)
        img = Image.new('RGB', (256, 256))
        img.putdata([
            (rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255))
            for _ in range(256 * 256)
        ])
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        png = buf.getvalue()
        assert len(png_to_jpeg_bytes(png)) < len(png)

    def test_empty_bytes_raises(self):
        with pytest.raises(ValueError):
            png_to_jpeg_bytes(b'')

    def test_garbage_bytes_raises(self):
        with pytest.raises(ValueError):
            png_to_jpeg_bytes(b'not an image')


@pytest.mark.django_db
class TestStudentImageProperty:
    def test_prefers_original_jpeg(self):
        page = GraphicNovelPageFactory()
        page.image.save('p.png', ContentFile(_png_bytes()), save=False)
        page.image_jpeg.save('p.jpg', ContentFile(png_to_jpeg_bytes(_png_bytes())), save=True)
        assert page.student_image.name.endswith('.jpg')
        assert page.student_image == page.image_jpeg

    def test_falls_back_to_png_when_jpeg_missing(self):
        page = GraphicNovelPageFactory()
        page.image.save('p.png', ContentFile(_png_bytes()), save=True)
        assert page.student_image == page.image

    def test_uses_edited_jpeg_when_selected(self):
        page = GraphicNovelPageFactory(use_edited_image=True)
        page.image.save('p.png', ContentFile(_png_bytes()), save=False)
        page.image_jpeg.save('p.jpg', ContentFile(png_to_jpeg_bytes(_png_bytes())), save=False)
        page.edited_image.save('e.png', ContentFile(_png_bytes()), save=False)
        page.edited_image_jpeg.save('e.jpg', ContentFile(png_to_jpeg_bytes(_png_bytes())), save=True)
        assert page.student_image == page.edited_image_jpeg

    def test_edited_selected_but_no_edited_jpeg_falls_back_to_edited_png(self):
        page = GraphicNovelPageFactory(use_edited_image=True)
        page.edited_image.save('e.png', ContentFile(_png_bytes()), save=True)
        assert page.student_image == page.edited_image


@pytest.mark.django_db
class TestBackfill:
    def test_backfill_writes_missing_jpeg(self):
        page = GraphicNovelPageFactory()
        page.image.save('p.png', ContentFile(_png_bytes()), save=True)
        assert not page.image_jpeg
        written = backfill_page_jpegs(page)
        page.refresh_from_db()
        assert 'image_jpeg' in written
        assert page.image_jpeg
        assert page.student_image == page.image_jpeg

    def test_backfill_is_idempotent(self):
        page = GraphicNovelPageFactory()
        page.image.save('p.png', ContentFile(_png_bytes()), save=False)
        page.image_jpeg.save('p.jpg', ContentFile(png_to_jpeg_bytes(_png_bytes())), save=True)
        assert backfill_page_jpegs(page) == []


@pytest.mark.django_db
class TestPipelineSavesJpeg:
    def _setup(self):
        job = GenerationJobFactory(input_words=['bright'])
        pack = WordPack.objects.create(word_set=job.word_set, label='Pack 1', order=0)
        novel = GraphicNovel.objects.create(
            pack=pack, title='Test Novel', synopsis='A test synopsis.',
            style_prompt='Readable comic art.', reading_level=650,
        )
        page = GraphicNovelPage.objects.create(
            novel=novel, page_number=1, panel_count=1,
            layout_description='Single splash page.',
            panel_descriptions=[{'panel_number': 1, 'narration': 'Bright!'}],
            vocab_words_used=['bright'],
        )
        return job, pack, page

    def test_generation_saves_jpeg_companion(self):
        from unittest.mock import patch
        job, pack, page = self._setup()
        with patch('vocabulary.services.llm_service.load_prompt_template',
                   return_value="Page {page_number} {panel_details}"), \
             patch('vocabulary.services.llm_service.call_openai_image',
                   return_value=_png_bytes(mode='RGB', size=(16, 16), color=(0, 0, 255))):
            _step_graphic_novel_images(job, [pack])
        page.refresh_from_db()
        assert page.image
        assert page.image_jpeg
        assert page.image_jpeg.name.endswith('.jpg')
        assert page.student_image == page.image_jpeg
