"""TikTok through TikTok Studio's web uploader."""

from playwright.async_api import Page

from poster.platforms.base import (
    UPLOAD_TIMEOUT_MS,
    ChallengeError,
    NotLoggedInError,
    Post,
    first_visible,
    looks_like_login,
    maybe_click,
    replace_text,
)

UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
# Selectors (data-e2e attributes first; they've outlived several redesigns).
FILE_INPUT = 'input[type="file"]'
CAPTION_BOXES = (
    'div.public-DraftEditor-content[contenteditable="true"]',
    '[contenteditable="true"]',
)
POST_BUTTON = 'button[data-e2e="post_video_button"]'
POST_NOW = "Post now"  # confirmation shown for some accounts
UPLOADED_TEXT = "Uploaded"
CAPTCHA = "#captcha-verify-container, .captcha_verify_container"


class TikTokUploader:
    name = "tiktok"
    login_url = "https://www.tiktok.com/login"

    async def check_login(self, page: Page) -> None:
        await page.goto(UPLOAD_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3_000)
        if looks_like_login(page.url):
            raise NotLoggedInError("TikTok redirected to log in")
        if await page.locator(CAPTCHA).count():
            raise ChallengeError("TikTok is showing a captcha")

    async def upload(self, page: Page, post: Post, dry_run: bool) -> str | None:
        if "tiktokstudio/upload" not in page.url:
            await page.goto(UPLOAD_URL, wait_until="domcontentloaded")
        await page.locator(FILE_INPUT).first.set_input_files(post.video, timeout=60_000)

        caption = await first_visible(
            *(page.locator(selector) for selector in CAPTION_BOXES), timeout=120_000
        )
        # The box starts out holding the file name.
        await replace_text(page, caption, post.caption)

        await page.get_by_text(UPLOADED_TEXT, exact=False).first.wait_for(timeout=UPLOAD_TIMEOUT_MS)
        button = page.locator(POST_BUTTON).first
        await page.wait_for_function(
            "el => !el.disabled && el.getAttribute('aria-disabled') !== 'true'",
            arg=await button.element_handle(),
            timeout=UPLOAD_TIMEOUT_MS,
        )
        if dry_run:
            return None
        await button.click()
        await maybe_click(page.get_by_role("button", name=POST_NOW), timeout=5_000)
        if await page.locator(CAPTCHA).count():
            raise ChallengeError("TikTok asked for a captcha while posting")
        # Studio moves to the content list once the post is accepted.
        await page.wait_for_url("**/tiktokstudio/content**", timeout=120_000)
        return None
