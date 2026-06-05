"""Image format helpers.

Currently provides PNG -> JPEG conversion used to produce lightweight,
student-facing variants of graphic novel page images. The full-resolution
PNG remains the source of truth for admins, editing, and cross-page
continuity; students load the smaller JPEG to save bandwidth on mobile.
"""
import io

from PIL import Image

DEFAULT_JPEG_QUALITY = 85
# JPEG has no alpha channel; transparent regions are flattened onto this color.
_FLATTEN_BACKGROUND = (255, 255, 255)


def png_to_jpeg_bytes(png_bytes, quality=DEFAULT_JPEG_QUALITY):
    """Convert PNG (or any Pillow-readable) image bytes to JPEG bytes.

    Transparency is flattened onto a white background since JPEG cannot store
    an alpha channel. Returns optimized JPEG bytes suitable for saving to an
    ImageField.

    Raises ValueError if the input bytes cannot be decoded as an image.
    """
    if not png_bytes:
        raise ValueError("No image bytes provided for JPEG conversion.")

    try:
        with Image.open(io.BytesIO(png_bytes)) as source:
            source.load()
            if source.mode in ('RGBA', 'LA') or (
                source.mode == 'P' and 'transparency' in source.info
            ):
                rgba = source.convert('RGBA')
                background = Image.new('RGB', rgba.size, _FLATTEN_BACKGROUND)
                background.paste(rgba, mask=rgba.split()[-1])
                image = background
            else:
                image = source.convert('RGB')

            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=quality, optimize=True)
            return buffer.getvalue()
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - normalize decode/encode failures
        raise ValueError(f"Could not convert image to JPEG: {exc}") from exc
