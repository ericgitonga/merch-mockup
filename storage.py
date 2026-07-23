"""Thin wrapper around Vercel Blob's plain REST API (put/get/delete).

This is the *stable*, documented part of Vercel Blob (unlike the
client-upload token-minting protocol, which is only implemented inside the
`@vercel/blob` Node package and isn't published as a versioned contract —
see api/blob-upload.ts for that half). Verified empirically against the
project's own Blob store:

    PUT  https://blob.vercel-storage.com/<pathname>
         headers: authorization: Bearer <token>, x-api-version: 7,
                  x-content-type: <mime>, x-add-random-suffix: 0|1
         -> 200 JSON {url, downloadUrl, pathname, contentType, contentDisposition}

    GET  <the returned url>              -> raw bytes, inline disposition
    GET  <the returned url>?download=1   -> raw bytes, attachment disposition

No SDK needed for either direction — a blob's own `url` (captured at put
time) is used for every later read, so nothing here hardcodes the store's
public subdomain.
"""

import os

import requests

BLOB_API_BASE = "https://blob.vercel-storage.com"
BLOB_API_VERSION = "7"


def _token():
    token = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not token:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN is not set")
    return token


def public_base_url():
    """The store's public read subdomain, derived from BLOB_READ_WRITE_TOKEN.

    Token shape is `vercel_blob_rw_<storeid>_<secret>`; the public host is
    `https://<storeid, lowercased>.public.blob.vercel-storage.com` — verified
    directly against this project's own store (a `put()` of `test/hello.txt`
    returned a URL on exactly this host). Deriving it this way means a later,
    separate request (e.g. GET /result/<token>) can construct a blob's URL
    from its pathname alone, without needing the put-time response in hand.
    """
    store_id = _token().split("_")[3]
    return f"https://{store_id.lower()}.public.blob.vercel-storage.com"


def blob_url(pathname):
    return f"{public_base_url()}/{pathname}"


def put_blob(pathname, data, content_type):
    """Upload bytes to Blob at a deterministic pathname. Returns the API's
    JSON response ({url, downloadUrl, pathname, contentType, ...})."""
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
    resp = requests.get(url, timeout=timeout)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.content
