"""YouTube Shorts through YouTube Studio's upload dialog. A vertical video under three
minutes is published as a Short automatically."""

from playwright.async_api import Page

from poster.platforms.base import (
    UPLOAD_TIMEOUT_MS,
    NotLoggedInError,
    Post,
    first_visible,
    looks_like_login,
    maybe_click,
    replace_text,
)

UPLOAD_URL = "https://www.youtube.com/upload"
# Selectors (YouTube Studio, polymer components with stable ids/names).
FILE_INPUT = 'input[type="file"]'
TITLE_BOX = "#title-textarea #textbox"
DESCRIPTION_BOX = "#description-textarea #textbox"
NOT_FOR_KIDS = 'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]'
NEXT = "#next-button"
DONE = "#done-button"
VISIBILITY = 'tp-yt-paper-radio-button[name="{name}"]'
VIDEO_LINK = "ytcp-video-info a"
CLOSE = "#close-button"


class YouTubeUploader:
    name = "youtube"
    login_url = "https://studio.youtube.com"

    def __init__(self, visibility: str = "public") -> None:
        self._visibility = visibility.upper()

    async def check_login(self, page: Page) -> None:
        await page.goto(self.login_url, wait_until="domcontentloaded")
        # Studio never goes network-idle (it keeps polling); wait for the redirect instead.
        await page.wait_for_timeout(4_000)
        if looks_like_login(page.url) or "studio.youtube.com" not in page.url:
            raise NotLoggedInError("YouTube Studio redirected to sign-in")

    async def upload(self, page: Page, post: Post, dry_run: bool) -> str | None:
        await page.goto(UPLOAD_URL, wait_until="domcontentloaded")
        await page.locator(FILE_INPUT).first.set_input_files(post.video, timeout=60_000)

        title = await first_visible(page.locator(TITLE_BOX), timeout=120_000)
        await replace_text(page, title, _with_shorts_tag(post.title))
        await replace_text(page, page.locator(DESCRIPTION_BOX).first, post.caption)
        await page.locator(NOT_FOR_KIDS).first.click()

        for _ in range(3):  # Details → Video elements → Checks → Visibility
            await page.locator(NEXT).first.click()
            await page.wait_for_timeout(1_000)
        await page.locator(VISIBILITY.format(name=self._visibility)).first.click()

        link = await page.locator(VIDEO_LINK).first.get_attribute("href", timeout=120_000)
        done = page.locator(DONE).first
        # "Save/Publish" enables once the upload (not processing) has finished.
        await page.wait_for_function(
            "el => !el.hasAttribute('disabled') && el.getAttribute('aria-disabled') !== 'true'",
            arg=await done.element_handle(),
            timeout=UPLOAD_TIMEOUT_MS,
        )
        if dry_run:
            return link
        await done.click()
        await maybe_click(page.locator(CLOSE), timeout=60_000)
        return link


def _with_shorts_tag(title: str) -> str:
    title = title or "Clip"
    return title if len(title) + 8 > 100 else f"{title} #Shorts"
