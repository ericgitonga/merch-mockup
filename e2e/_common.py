"""Shared helpers for the Playwright E2E smoke suite.

Written against the Python `playwright` package (already present in the `ds`
conda env, browsers pre-cached), matching the umoja-voices e2e convention.
Run each spec directly, or all of them via `run.py`:

    conda run -n ds python e2e/run.py
    conda run -n ds python e2e/test_generate.py

BASE_URL defaults to local dev; CI overrides it to point at a gunicorn
server started in .github/workflows/e2e.yml — the same entrypoint used in
render.yaml, not a hand-run dev server.

merch-mockup has no accounts/database, so unlike umoja-voices' _common.py
there's no login/session caching here — every request is anonymous.
"""

import os
import re
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_PHOTO = str(FIXTURES_DIR / "sample.jpg")
NOT_A_PHOTO = str(FIXTURES_DIR / "not_a_photo.txt")

RESULT_TOKEN_RE = re.compile(r"/result/([0-9a-f]{32})")


@contextmanager
def browser_page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(base_url=BASE_URL)
            yield page
        finally:
            browser.close()


def submit_generate_form(page, *, photo=SAMPLE_PHOTO, top_text="",
                         bottom_text="", filename="", text_colour="White",
                         shirt_colour=None):
    """Load the form, fill it out, and submit. Caller inspects page.url /
    page.content() afterwards — a successful generate redirects to
    /result/<token>; a validation failure re-renders / with a flash message.
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
    page.wait_for_load_state("networkidle")


def result_token(page):
    """Extract the result token from the current page URL, or None."""
    m = RESULT_TOKEN_RE.search(page.url)
    return m.group(1) if m else None
