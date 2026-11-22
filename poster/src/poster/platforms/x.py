"""X (Twitter) through the web composer. The post text is the caption, cut to X's
280-character limit at a word."""

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

COMPOSE_URL = "https://x.com/compose/post"
# Selectors (data-testid attributes; X keeps these stable across redesigns).
FILE_INPUT = 'input[type="file"][data-testid="fileInput"], input[type="file"]'
TEXT_BOXES = ('[data-testid="tweetTextarea_0"]', 'div[role="textbox"][contenteditable="true"]')
POST_BUTTON = '[data-testid="tweetButton"], [data-testid="tweetButtonInline"]'
#: Shown while the attached video is still uploading/processing.
UPLOAD_PROGRESS = '[data-testid="progressBar"], [role="progressbar"]'
POSTED_TOAST = '[data-testid="toast"]'
CHALLENGE = 'iframe[src*="arkoselabs"], iframe[title*="challenge" i]'

#: X counts every character (links and emoji differ slightly; this stays clear of it).
MAX_CHARS = 280


def fit_text(text: str, limit: int = MAX_CHARS) -> str:
    """``text`` cut at a word to fit ``limit`` characters."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip()
    return f"{cut}…"


class XUploader:
    name = "x"
    login_url = "https://x.com/i/flow/login"

    async def check_login(self, page: Page) -> None:
        await page.goto(COMPOSE_URL, wait_until="domcontentloaded")
        await page.wait_for_timeout(3_000)
        if looks_like_login(page.url) or "/i/flow/login" in page.url:
            raise NotLoggedInError("X redirected to log in")
        if await page.locator(CHALLENGE).count():
            raise ChallengeError("X is showing a verification challenge")

    async def upload(self, page: Page, post: Post, dry_run: bool) -> str | None:
        if "compose/post" not in page.url:
            await page.goto(COMPOSE_URL, wait_until="domcontentloaded")
        box = await first_visible(*(page.locator(s) for s in TEXT_BOXES), timeout=60_000)
        await page.locator(FILE_INPUT).first.set_input_files(post.video, timeout=60_000)
        await replace_text(page, box, fit_text(post.caption))

        button = page.locator(POST_BUTTON).first
        await button.wait_for(state="visible", timeout=60_000)
        # The Post button only enables once the video has uploaded.
        await page.wait_for_function(
            "el => !el.disabled && el.getAttribute('aria-disabled') !== 'true'",
            arg=await button.element_handle(),
            timeout=UPLOAD_TIMEOUT_MS,
        )
        if dry_run:
            return None
        await button.click()
        # The composer closes and a "Your post was sent" toast offers a link to it.
        toast = page.locator(POSTED_TOAST).first
        await toast.wait_for(state="visible", timeout=UPLOAD_TIMEOUT_MS)
        link = await toast.locator('a[href*="/status/"]').first.get_attribute(
            "href", timeout=10_000
        )
        return f"https://x.com{link}" if link and link.startswith("/") else link
