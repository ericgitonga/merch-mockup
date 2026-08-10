"""Zip-on-demand packaging logic (`app._build_zip`)."""

import zipfile
from io import BytesIO

from app import _build_zip


def test_zip_contains_each_file_under_its_arcname():
    files = [
        ("design.tiff", b"tiff-bytes"),
        ("design.png", b"png-bytes"),
        ("design_mockup.jpg", b"jpg-bytes"),
    ]

    zip_bytes = _build_zip(files)

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        assert sorted(zf.namelist()) == sorted(name for name, _ in files)
        for name, data in files:
            assert zf.read(name) == data


def test_empty_file_list_produces_a_valid_empty_zip():
    zip_bytes = _build_zip([])
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        assert zf.namelist() == []
