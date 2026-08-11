"""Non-image / decompression-bomb rejection (`app._crop_photo`).

Locks in the exception types `/generate`'s try/except (added for issue #14)
relies on: a non-image upload must raise `UnidentifiedImageError`, and an
image whose pixel count exceeds Pillow's decompression-bomb guard must raise
`DecompressionBombError` — either would otherwise surface as a bare 500
instead of the app's normal user-facing error path.
"""

from pathlib import Path

import pytest
from PIL import Image, UnidentifiedImageError

from app import _crop_photo

FIXTURES_DIR = Path(__file__).parent.parent / "e2e" / "fixtures"
NOT_A_PHOTO = FIXTURES_DIR / "not_a_photo.txt"
SAMPLE_PHOTO = FIXTURES_DIR / "sample.jpg"


def test_non_image_upload_raises_unidentified_image_error():
    with pytest.raises(UnidentifiedImageError):
        _crop_photo(NOT_A_PHOTO, pw=100)


def test_oversized_image_raises_decompression_bomb_error(monkeypatch):
    # sample.jpg is a small, legitimate photo; lowering the pixel-count
    # threshold below its actual size exercises the same guard a real
    # decompression bomb would trip, without needing a multi-gigapixel fixture.
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 100)
    with pytest.raises(Image.DecompressionBombError):
        _crop_photo(SAMPLE_PHOTO, pw=100)


def test_valid_photo_crops_to_a_square_of_the_requested_width():
    result = _crop_photo(SAMPLE_PHOTO, pw=150)
    assert result.size == (150, 150)
    assert result.mode == "RGB"
