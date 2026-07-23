"""Shared helpers for the Playwright E2E smoke suite.

Written against the Python `playwright` package (already present in the `ds`
conda env, browsers pre-cached), matching the umoja-voices e2e convention.
Run each spec directly, or all of them via `run.py`:

    conda run -n ds python e2e/run.py
    conda run -n ds python e2e/test_generate.py

BASE_URL defaults to local dev; CI overrides it to point at a real Vercel
Preview deployment of the PR (`vercel deploy --target preview` in
.github/workflows/e2e.yml) — this app's mixed Python + Node Functions and
its dependency on real Vercel Blob storage aren't something `vercel dev`
or a hand-run local server can faithfully stand in for. Preview
deployments sit behind Vercel's Deployment Protection (SSO); set
VERCEL_BYPASS_SECRET (a "Protection Bypass for Automation" secret from the
project's settings) to get past it.

merch-mockup has no accounts/database, so unlike umoja-voices' _common.py
there's no login/session caching here — every request is anonymous.
"""

import os
import re
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")
BYPASS_SECRET = os.environ.get("VERCEL_BYPASS_SECRET", "")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PHOTO = str(FIXTURES_DIR / "sample.jpg")
NOT_A_PHOTO = str(FIXTURES_DIR / "not_a_photo.txt")

RESULT_TOKEN_RE = re.compile(r"/result/([0-9a-f]{32})")


def bypass_headers():
    """Kept for callers that need it explicitly; browser_page() no longer
    needs this itself (see below) — sending it as a header on every request
    breaks CORS on the cross-origin presigned Blob PUT (confirmed directly:
    Chrome blocked the preflight because x-vercel-protection-bypass isn't in
    that endpoint's Access-Control-Allow-Headers). A plain GET like
    /_health still accepts it fine.
    """
    if not BYPASS_SECRET:
        return {}
    return {"x-vercel-protection-bypass": BYPASS_SECRET}


@contextmanager
def browser_page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(base_url=BASE_URL)
            if BYPASS_SECRET:
                # Set the header just long enough to mint Vercel's bypass
                # cookie for our own domain, then drop it — later requests
                # (including the cross-origin presigned PUT) never see it,
                # only the cookie, which the browser scopes correctly on
                # its own and never sends to blob.vercel-storage.com/vercel.com.
                page.set_extra_http_headers({
                    "x-vercel-protection-bypass": BYPASS_SECRET,
                    "x-vercel-set-bypass-cookie": "true",
                })
                page.goto("/")
                page.set_extra_http_headers({})
            yield page
        finally:
            browser.close()


def submit_generate_form(page, *, photo=SAMPLE_PHOTO, top_text="",
                         bottom_text="", filename="", text_colour="White",
                         shirt_colour=None):
    """Load the form, fill it out, and submit.

    The photo goes straight from the browser to Blob storage via the page's
    own JS (api/blob-upload.ts mints a presigned URL; see
    templates/index.html's inline <script>) before the real form submission
    fires — so this waits for either a redirect to /result/<token> (success)
    or the #upload-status text settling on an error (client-side upload
    rejected, or the Flask-side validation flash after a real redirect back
    to /). Caller inspects page.url / page.content() afterwards.
    """
    page.goto("/")
    if photo:
        page.set_input_files("#photo", photo)
    if top_text:
        page.fill("#top_text", top_text)
    if bottom_text:
        page.fill("#bottom_text", bottom_text)
    if filename:
        page.fill("#filename", filename)
    if text_colour:
        page.check(f"input[name='text_colour'][value='{text_colour}']")
    if shirt_colour:
        page.select_option("#shirt_colour", shirt_colour)

    page.click("button[type=submit]")

    # Three possible end states: (a) client-side upload rejected — no
    # navigation happens at all, #submit-btn re-enables; (b) Flask-side
    # validation failure — a real navigation back to a page with a flash
    # message; (c) success — a real navigation to /result/<token>. All three
    # are covered by "we've navigated to /result/, or the button is no
    # longer disabled" (a fresh page load always starts with an enabled
    # button, so (b) and (c) satisfy this too).
    page.wait_for_function(
        "() => location.pathname.includes('/result/') "
        "|| document.getElementById('submit-btn').disabled === false",
        timeout=20_000,
    )
    page.wait_for_load_state("networkidle")


def result_token(page):
    """Extract the result token from the current page URL, or None."""
    m = RESULT_TOKEN_RE.search(page.url)
    return m.group(1) if m else None
