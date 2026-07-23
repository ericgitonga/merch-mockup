"""Validation error paths.

No more /preview or /download proxy routes to 404-test here — downloads are
now direct Blob URLs (see test_generate.py), so there's nothing on the Flask
side left to path-traverse. What remains Flask-side is /generate's own
defense-in-depth check on `photo_pathname` (in case a tampered request ever
skips the browser's own upload flow) and /result/<token>'s handling of a
token whose Blob metadata was never written (or was cleaned up).
"""

from _common import NOT_A_PHOTO, browser_page, submit_generate_form

BOGUS_TOKEN = "0" * 32       # well-formed (32 hex chars) but never issued
MALFORMED_TOKEN = "not-a-token"


def test_missing_name_shows_flash_error():
    with browser_page() as page:
        submit_generate_form(page, bottom_text="", filename="")
        assert "/result/" not in page.url
        assert "Please enter a bottom text or fill in" in page.content()


def test_disallowed_file_extension_rejected_client_side():
    with browser_page() as page:
        submit_generate_form(page, photo=NOT_A_PHOTO, bottom_text="Flagrant")
        assert "/result/" not in page.url
        assert "Unsupported content type" in page.locator("#upload-status").inner_text()


def test_tampered_photo_pathname_rejected_server_side():
    """Defense in depth: /generate itself validates photo_pathname's shape,
    independent of whatever the browser's own upload JS would ever send.

    Still has to pick a file — the file input's `required` attribute
    silently blocks even a programmatic requestSubmit() otherwise — but
    setting photo_pathname directly beforehand means our own upload JS sees
    it's already "uploaded" and never touches the file's actual content.
    """
    with browser_page() as page:
        page.goto("/")
        page.set_input_files("#photo", NOT_A_PHOTO)
        page.fill("#bottom_text", "Flagrant")
        page.eval_on_selector(
            "#photo_pathname", "el => el.value = '../../etc/passwd'"
        )
        page.evaluate("document.getElementById('generate-form').requestSubmit()")
        page.wait_for_load_state("networkidle")
        assert "/result/" not in page.url
        assert "upload looks invalid" in page.content()


def test_unknown_result_token_redirects_home():
    with browser_page() as page:
        page.goto(f"/result/{BOGUS_TOKEN}")
        assert "/result/" not in page.url
        assert "expired" in page.content()

        resp = page.goto(f"/result/{MALFORMED_TOKEN}")
        assert resp.status == 404


TESTS = [
    test_missing_name_shows_flash_error,
    test_disallowed_file_extension_rejected_client_side,
    test_tampered_photo_pathname_rejected_server_side,
    test_unknown_result_token_redirects_home,
]

if __name__ == "__main__":
    for t in TESTS:
        t()
        print(f"PASS {t.__name__}")
