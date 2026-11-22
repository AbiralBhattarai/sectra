"""Facebook Reels through facebook.com/reels/create. Posts as whichever profile or Page
the browser profile is currently acting as (switch to your Page once while logging in)."""

from playwright.async_api import Page

from poster.platforms.base import (
    UPLOAD_TIMEOUT_MS,
    ChallengeError,
    NotLoggedInError,
    Post,
    first_visible,
    looks_like_login,
    replace_text,
)

CREATE_URL = "https://www.facebook.com/reels/create"
# Selectors (roles and visible text).
FILE_INPUT = 'input[type="file"]'
NEXT = "Next"
DESCRIPTION_BOX = 'div[role="textbox"][contenteditable="true"]'
PUBLISH = "Publish"
PUBLISHED = ("Your reel is published", "Reel published", "Your reel is being processed")
LOGIN_FORM = 'input[name="email"]'


class FacebookUploader:
    name = "facebook"
    login_url = "https://www.facebook.com/login"

    async def check_login(self, page: Page) -> None:
        await page.goto(CREATE_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3_000)
        if looks_like_login(page.url) or await page.locator(LOGIN_FORM).count():
            raise NotLoggedInError("Facebook shows the login form")
        if "checkpoint" in page.url:
            raise ChallengeError("Facebook wants the account verified")

    async def upload(self, page: Page, post: Post, dry_run: bool) -> str | None:
        if "reels/create" not in page.url:
            await page.goto(CREATE_URL, wait_until="domcontentloaded")
        await page.locator(FILE_INPUT).first.set_input_files(post.video, timeout=60_000)
        for _ in range(2):  # upload → edit → details
            await page.get_by_role("button", name=NEXT, exact=True).first.click(
                timeout=UPLOAD_TIMEOUT_MS
            )
            await page.wait_for_timeout(1_500)

        description = await first_visible(page.locator(DESCRIPTION_BOX), timeout=60_000)
        await replace_text(page, description, post.caption)
        publish = page.get_by_role("button", name=PUBLISH, exact=True).first
        await publish.wait_for(timeout=UPLOAD_TIMEOUT_MS)
        if dry_run:
            return None
        await publish.click()
        done = page.get_by_text(PUBLISHED[0])
        for text in PUBLISHED[1:]:
            done = done.or_(page.get_by_text(text))
        await done.first.wait_for(timeout=UPLOAD_TIMEOUT_MS)
        return None
