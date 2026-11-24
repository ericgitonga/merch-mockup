"""Tests for local offline storage fallback and local upload routes."""

import io
import json
import zipfile
from pathlib import Path
from PIL import Image
import pytest

import storage
from app import app


@pytest.fixture
def local_storage(tmp_path, monkeypatch):
    """Point storage to a temporary directory in local mode."""
    monkeypatch.setattr(storage, "LOCAL_STORAGE_DIR", tmp_path)
    monkeypatch.setenv("USE_LOCAL_STORAGE", "1")
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    assert storage.is_local() is True
    return tmp_path


@pytest.fixture
def client(local_storage):
    """Configured Flask test client."""
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client


def test_local_storage_put_get_delete(local_storage):
    data = b"sample image bytes"
    pathname = "uploads/test_sample.jpg"

    res = storage.put_blob(pathname, data, "image/jpeg")
    assert res["pathname"] == pathname
    assert res["url"] == f"/local-blob/{pathname}"
    assert res["downloadUrl"] == f"/local-blob/{pathname}?download=1"

    saved_file = local_storage / pathname
    assert saved_file.exists()
    assert saved_file.read_bytes() == data

    # Read back via get_blob_bytes
    fetched = storage.get_blob_bytes(res["url"])
    assert fetched == data

    # Read back with download query param
    fetched_dl = storage.get_blob_bytes(res["downloadUrl"])
    assert fetched_dl == data

    # Delete
    storage.delete_blobs([res["url"]])
    assert not saved_file.exists()
    assert storage.get_blob_bytes(res["url"]) is None


def test_api_blob_upload_validation(client):
    # Invalid content type
    resp = client.post("/api/blob-upload", json={"contentType": "application/pdf"})
    assert resp.status_code == 400
    assert "supported" in resp.get_json()["error"]

    # Valid JPEG
    resp = client.post("/api/blob-upload", json={"contentType": "image/jpeg"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["pathname"].startswith("uploads/")
    assert data["pathname"].endswith(".jpg")
    assert "presignedUrl" in data


def test_full_local_flow_upload_generate_download(client, local_storage):
    # 1. Create a small valid test image
    img = Image.new("RGB", (200, 200), color=(120, 180, 220))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    # 2. Request upload endpoint
    upload_prep = client.post("/api/blob-upload", json={"contentType": "image/jpeg"}).get_json()
    presigned_url = upload_prep["presignedUrl"]
    photo_pathname = upload_prep["pathname"]

    # 3. PUT image to local upload endpoint
    put_resp = client.put(presigned_url, data=img_bytes, content_type="image/jpeg")
    assert put_resp.status_code == 200
    assert (local_storage / photo_pathname).read_bytes() == img_bytes

    # 4. Generate
    gen_resp = client.post(
        "/generate",
        data={
            "photo_pathname": photo_pathname,
            "top_text": "Local Test",
            "bottom_text": "Dudu",
            "text_colour": "White",
            "shirt_colour": "Black",
        },
    )
    assert gen_resp.status_code == 302
    assert "/result/" in gen_resp.headers["Location"]
    token = gen_resp.headers["Location"].split("/result/")[1]

    # 5. Access result page
    result_page = client.get(f"/result/{token}")
    assert result_page.status_code == 200
    assert b"Local Test" in result_page.data

    # 6. Verify result files exist in local storage
    meta_bytes = (local_storage / f"results/{token}/meta.json").read_bytes()
    meta = json.loads(meta_bytes)
    assert meta["slug"] == "dudu"
    assert (local_storage / f"results/{token}/dudu.tiff").exists()
    assert (local_storage / f"results/{token}/dudu.png").exists()
    assert (local_storage / f"results/{token}/dudu_mockup.jpg").exists()

    # 7. Download zip
    dl_resp = client.get(f"/download/{token}")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["Content-Type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(dl_resp.data)) as zf:
        names = zf.namelist()
        assert "dudu.tiff" in names
        assert "dudu.png" in names
        assert "dudu_mockup.jpg" in names

    # 8. Result files cleaned up on download
    assert not (local_storage / f"results/{token}/dudu.tiff").exists()
