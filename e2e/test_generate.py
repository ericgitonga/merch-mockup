"""Golden path: upload a photo, generate, previews render, downloads work.

Downloads/previews are read directly off the rendered page (real Blob URLs)
rather than constructed by the test — the app hands back whatever Blob
actually returned, so there's nothing to guess about the store's subdomain
or pathname scheme.
"""

from _common import bypass_headers, browser_page, result_token, submit_generate_form


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

        preview_urls = page.locator(".results-grid img").evaluate_all(
            "imgs => imgs.map(img => img.src)"
        )
        assert len(preview_urls) == 2
        for url in preview_urls:
            resp = page.request.get(url, headers=bypass_headers())
            assert resp.status == 200
            assert resp.headers["content-type"] == "image/jpeg"

        download_links = page.locator(".downloads-card a").evaluate_all(
            "as => as.map(a => ({href: a.href, text: a.textContent}))"
        )
        assert len(download_links) == 3

        expected = {
            "TIFF (print-ready)": ("image/tiff", "flagrant.tiff"),
            "PNG (transparent)":  ("image/png", "flagrant.png"),
            "Mockup JPG":         ("image/jpeg", "flagrant_mockup.jpg"),
        }
        for link in download_links:
            label = link["text"].strip()
            mimetype, download_name = expected[label]
            # The TIFF in particular can run ~20MB (LZW barely compresses a
            # busy photographic 2400x2900 canvas — confirmed against a real
            # deployment) — give it real time on a slow connection.
            resp = page.request.get(link["href"], headers=bypass_headers(), timeout=120_000)
            assert resp.status == 200
            assert resp.headers["content-type"] == mimetype
            assert download_name in resp.headers["content-disposition"]
            assert "attachment" in resp.headers["content-disposition"]


def test_generate_with_filename_only_no_bottom_text():
    with browser_page() as page:
        submit_generate_form(page, top_text="", bottom_text="",
                             filename="My Ant Design")
        token = result_token(page)
        assert token, f"expected a redirect to /result/<token>, got {page.url}"

        png_link = page.locator(".downloads-card a", has_text="PNG").get_attribute("href")
        resp = page.request.get(png_link, headers=bypass_headers())
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
