"""Validation error paths and token-based route 404s."""

from _common import BASE_URL, NOT_A_PHOTO, browser_page, submit_generate_form

BOGUS_TOKEN = "0" * 32       # well-formed (32 hex chars) but never issued
MALFORMED_TOKEN = "not-a-token"


def test_missing_name_shows_flash_error():
    with browser_page() as page:
        submit_generate_form(page, bottom_text="", filename="")
        assert "/result/" not in page.url
        assert "Please enter a bottom text or fill in" in page.content()


def test_disallowed_file_extension_rejected():
    with browser_page() as page:
        submit_generate_form(page, photo=NOT_A_PHOTO, bottom_text="Flagrant")
        assert "/result/" not in page.url
        assert "Unsupported file type" in page.content()


def test_unknown_result_token_redirects_home():
    with browser_page() as page:
        page.goto(f"/result/{BOGUS_TOKEN}")
        assert "/result/" not in page.url
        assert "expired" in page.content()


def test_unknown_and_malformed_tokens_404_on_file_routes():
    with browser_page() as page:
        for token in (BOGUS_TOKEN, MALFORMED_TOKEN):
            resp = page.request.get(f"{BASE_URL}/preview/{token}/design",
                                    max_redirects=0, fail_on_status_code=False)
            assert resp.status == 404, f"preview/{token} -> {resp.status}"

            resp = page.request.get(f"{BASE_URL}/download/{token}/png",
                                    max_redirects=0, fail_on_status_code=False)
            assert resp.status == 404, f"download/{token} -> {resp.status}"


TESTS = [
    test_missing_name_shows_flash_error,
    test_disallowed_file_extension_rejected,
    test_unknown_result_token_redirects_home,
    test_unknown_and_malformed_tokens_404_on_file_routes,
]

if __name__ == "__main__":
    for t in TESTS:
        t()
        print(f"PASS {t.__name__}")
