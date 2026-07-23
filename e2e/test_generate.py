"""Golden path: upload a photo, generate, previews render, download works.

Downloads/previews are read directly off the rendered page (real Blob URLs
and the app's own /download/<token> route) rather than constructed by the
test — the app hands back whatever it actually generated, so there's
nothing to guess about the store's subdomain or pathname scheme.
"""

import io
import zipfile

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
        assert len(download_links) == 1
        assert download_links[0]["text"].strip() == "Download design"

        # The TIFF inside can run ~20MB (LZW barely compresses a busy
        # photographic 2400x2900 canvas — confirmed against a real
        # deployment) — give the zip real time on a slow connection.
        resp = page.request.get(
            download_links[0]["href"], headers=bypass_headers(), timeout=120_000
        )
        assert resp.status == 200
        assert resp.headers["content-type"] == "application/zip"
        assert "flagrant_design.zip" in resp.headers["content-disposition"]
        assert "attachment" in resp.headers["content-disposition"]

        zf = zipfile.ZipFile(io.BytesIO(resp.body()))
        names = set(zf.namelist())
        assert names == {"flagrant.tiff", "flagrant.png", "flagrant_mockup.jpg"}
        for name in names:
            assert zf.getinfo(name).file_size > 0


def test_generate_with_filename_only_no_bottom_text():
    with browser_page() as page:
        submit_generate_form(page, top_text="", bottom_text="",
                             filename="My Ant Design")
        token = result_token(page)
        assert token, f"expected a redirect to /result/<token>, got {page.url}"

        download_link = page.locator(".downloads-card a").get_attribute("href")
        resp = page.request.get(download_link, headers=bypass_headers(), timeout=120_000)
        assert resp.status == 200
        assert "my_ant_design_design.zip" in resp.headers["content-disposition"]

        zf = zipfile.ZipFile(io.BytesIO(resp.body()))
        assert set(zf.namelist()) == {
            "my_ant_design.tiff", "my_ant_design.png", "my_ant_design_mockup.jpg",
        }


TESTS = [
    test_generate_with_both_texts_and_downloads,
    test_generate_with_filename_only_no_bottom_text,
]

if __name__ == "__main__":
    for t in TESTS:
        t()
        print(f"PASS {t.__name__}")
