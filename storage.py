"""Storage adapter for Vercel Blob with local disk fallback.

In production on Vercel, wraps Vercel Blob's plain REST API (put/get/delete).
In local offline development (when BLOB_READ_WRITE_TOKEN is unset or
USE_LOCAL_STORAGE=1), transparently persists files to .local_storage/ and
serves them via /local-blob/<path>.
"""

import os
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent
LOCAL_STORAGE_DIR = Path(os.environ.get("LOCAL_STORAGE_DIR", BASE_DIR / ".local_storage"))

BLOB_API_BASE = "https://blob.vercel-storage.com"
BLOB_API_VERSION = "7"


def is_local():
    """Returns True if local disk storage should be used instead of Vercel Blob."""
    if os.environ.get("USE_LOCAL_STORAGE") == "1":
        return True
    if os.environ.get("VERCEL") == "1":
        return False
    return not bool(os.environ.get("BLOB_READ_WRITE_TOKEN"))


def _token():
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN is not set")
    return token


def public_base_url():
    """The store's public read subdomain, derived from BLOB_READ_WRITE_TOKEN
    or local URL prefix."""
    if is_local():
        return "/local-blob"
    store_id = _token().split("_")[3]
    return f"https://{store_id.lower()}.public.blob.vercel-storage.com"


def blob_url(pathname):
    pathname = pathname.lstrip("/")
    return f"{public_base_url()}/{pathname}"


def put_blob(pathname, data, content_type):
    """Upload bytes to Blob at a deterministic pathname. Returns the API's
    JSON response ({url, downloadUrl, pathname, contentType, ...})."""
    pathname = pathname.lstrip("/")
    if is_local():
        dest = LOCAL_STORAGE_DIR / pathname
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        url = f"/local-blob/{pathname}"
        return {
            "url": url,
            "downloadUrl": f"{url}?download=1",
            "pathname": pathname,
            "contentType": content_type,
        }

    resp = requests.put(
        f"{BLOB_API_BASE}/{pathname}",
        data=data,
        headers={
            "authorization": f"Bearer {_token()}",
            "x-api-version": BLOB_API_VERSION,
            "x-content-type": content_type,
            "x-add-random-suffix": "0",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_blob_bytes(url, timeout=30):
    """Fetch a blob's raw bytes. Returns None if not found (404)."""
    if not url:
        return None

    if "/local-blob/" in url or url.startswith("/local-blob"):
        idx = url.find("/local-blob/")
        rel_path = url[idx + len("/local-blob/"):].split("?")[0]
        dest = LOCAL_STORAGE_DIR / rel_path
        if not dest.is_file():
            return None
        return dest.read_bytes()

    resp = requests.get(url, timeout=timeout)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content


def delete_blobs(urls, timeout=30):
    """Delete one or more blobs by their `url`."""
    if not urls:
        return

    remote_urls = []
    for u in urls:
        if not u:
            continue
        if "/local-blob/" in u or u.startswith("/local-blob"):
            idx = u.find("/local-blob/")
            rel_path = u[idx + len("/local-blob/"):].split("?")[0]
            dest = LOCAL_STORAGE_DIR / rel_path
            if dest.is_file():
                dest.unlink(missing_ok=True)
        else:
            remote_urls.append(u)

    if remote_urls:
        resp = requests.post(
            f"{BLOB_API_BASE}/delete",
            json={"urls": remote_urls},
            headers={"authorization": f"Bearer {_token()}"},
            timeout=timeout,
        )
        resp.raise_for_status()
