"""Form fields stay populated after a generation, until Clear is used.

Covers issue #25: previously /generate's redirect to /result/<token> always
re-rendered a blank form, forcing the user to retype everything (including
re-uploading the photo) just to try a different colour. Now the submitted
values — and the already-uploaded photo's Blob pathname — are round-tripped
through the result Blob's meta.json and rendered back into the form.
"""

from _common import browser_page, result_token, submit_generate_form


def test_fields_and_photo_persist_after_generate():
    with browser_page() as page:
        submit_generate_form(
            page, top_text="Fiery hot ant", bottom_text="Flagrant",
            text_colour="Red", shirt_colour="Deep Navy",
        )
        token = result_token(page)
        assert token, f"expected a redirect to /result/<token>, got {page.url}"

        assert page.locator("#top_text").input_value() == "Fiery hot ant"
        assert page.locator("#bottom_text").input_value() == "Flagrant"
        assert page.locator("input[name='text_colour'][value='Red']").is_checked()
        assert page.locator("#shirt_colour").input_value() == "Deep Navy"
        assert page.locator("#photo_pathname").input_value() != ""


def test_regenerate_with_new_colour_reuses_photo_without_reselecting():
    with browser_page() as page:
        submit_generate_form(page, bottom_text="Flagrant", text_colour="White")
        token1 = result_token(page)
        assert token1

        # Don't touch the (now-empty) file input — just change a colour and
        # generate again, exactly the "cycle through colours" workflow from
        # issue #25.
        page.check("input[name='text_colour'][value='Blue']")
        page.click("button[type=submit]")
        page.wait_for_function(
            "() => location.pathname.includes('/result/')", timeout=20_000,
        )
        page.wait_for_load_state("networkidle")

        token2 = result_token(page)
        assert token2 and token2 != token1


def test_clear_resets_the_form():
    with browser_page() as page:
        submit_generate_form(
            page, top_text="Fiery hot ant", bottom_text="Flagrant",
            text_colour="Red",
        )
        assert result_token(page)

        page.click("text=Clear")
        page.wait_for_load_state("networkidle")

        assert "/result/" not in page.url
        assert page.locator("#top_text").input_value() == ""
        assert page.locator("#bottom_text").input_value() == ""
        assert page.locator("#photo_pathname").input_value() == ""
        assert page.locator("input[name='text_colour'][value='White']").is_checked()


TESTS = [
    test_fields_and_photo_persist_after_generate,
    test_regenerate_with_new_colour_reuses_photo_without_reselecting,
    test_clear_resets_the_form,
]

if __name__ == "__main__":
    for t in TESTS:
        t()
        print(f"PASS {t.__name__}")
