"""Golden path: upload a photo, generate, previews render, downloads work."""

from _common import BASE_URL, browser_page, result_token, submit_generate_form


def test_generate_with_both_texts_and_downloads():
    with browser_page() as page:
        submit_generate_form(
            page, top_text="Fiery hot ant", bottom_text="Flagrant",
            text_colour="White", shirt_colour="Deep Navy",
        )
        token = result_token(page)
        assert token, f"expected a redirect to /result/<token>, got {page.url}"

        assert page.locator("h2", has_text="Design preview").is_visible()
        assert page.locator("h2", has_text="T-shirt mockup").is_visible()

        for kind in ("design", "mockup"):
            resp = page.request.get(f"{BASE_URL}/preview/{token}/{kind}")
            assert resp.status == 200
            assert resp.headers["content-type"] == "image/jpeg"

        downloads = {
            "tiff":   ("image/tiff", "flagrant.tiff"),
            "png":    ("image/png", "flagrant.png"),
            "mockup": ("image/jpeg", "flagrant_mockup.jpg"),
        }
        for kind, (mimetype, download_name) in downloads.items():
            resp = page.request.get(f"{BASE_URL}/download/{token}/{kind}")
            assert resp.status == 200
            assert resp.headers["content-type"] == mimetype
            assert download_name in resp.headers["content-disposition"]


def test_generate_with_filename_only_no_bottom_text():
    with browser_page() as page:
        submit_generate_form(page, top_text="", bottom_text="",
                             filename="My Ant Design")
        token = result_token(page)
        assert token, f"expected a redirect to /result/<token>, got {page.url}"

        resp = page.request.get(f"{BASE_URL}/download/{token}/png")
        assert resp.status == 200
        assert "my_ant_design.png" in resp.headers["content-disposition"]


TESTS = [
    test_generate_with_both_texts_and_downloads,
    test_generate_with_filename_only_no_bottom_text,
]

if __name__ == "__main__":
    for t in TESTS:
        t()
        print(f"PASS {t.__name__}")
