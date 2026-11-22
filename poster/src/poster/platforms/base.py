"""What every platform uploader provides, plus shared Playwright helpers.

Sites change their markup often. Each uploader keeps its selectors in one block at the
top of its module, preferring roles and visible text over CSS classes; when a post
fails, ``poster/logs`` gets a screenshot of the page to fix them against."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

#: Video upload + processing can take a while on a slow connection.
UPLOAD_TIMEOUT_MS = 15 * 60_000


class NotLoggedInError(Exception):
    """The profile has no (valid) session: run `poster login <platform>`."""


class ChallengeError(Exception):
    """The site wants a human (captcha, verification): stop for this platform."""


@dataclass
class Post:
    video: Path
    caption: str
    #: Short title for platforms that have one (YouTube).
    title: str


class Uploader(Protocol):
    name: str
    #: Where `poster login` opens.
    login_url: str

    async def check_login(self, page: Page) -> None:
        """Raise ``NotLoggedInError`` / ``ChallengeError`` when posting can't proceed."""
        ...

    async def upload(self, page: Page, post: Post, dry_run: bool) -> str | None:
        """Upload and publish; returns the post's URL when the site shows it. With
        ``dry_run`` everything is filled in but the final publish click isn't made."""
        ...


def title_from(caption: str, limit: int = 100) -> str:
    """The caption's first line without hashtags, cut at a word: a title for YouTube."""
    first = caption.strip().splitlines()[0] if caption.strip() else ""
    text = " ".join(w for w in first.split() if not w.startswith("#")) or first
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0]


async def first_visible(*locators: Locator, timeout: int = 30_000) -> Locator:
    """The first of several alternative locators to show up (old and new site layouts)."""
    combined = locators[0]
    for other in locators[1:]:
        combined = combined.or_(other)
    await combined.first.wait_for(state="visible", timeout=timeout)
    for locator in locators:
        if await locator.first.is_visible():
            return locator.first
    return combined.first


async def maybe_click(locator: Locator, timeout: int = 3_000) -> bool:
    """Click ``locator`` if it appears within ``timeout`` (optional dialogs, tips)."""
    try:
        await locator.first.click(timeout=timeout)
        return True
    except PlaywrightTimeout:
        return False


async def replace_text(page: Page, box: Locator, text: str) -> None:
    """Replace a (rich) text box's content by typing, the way a person would, so the
    site's editor sees real key events (hashtag pickers, counters)."""
    await box.click()
    await page.keyboard.press("ControlOrMeta+A")
    await page.keyboard.press("Delete")
    for line_number, line in enumerate(text.splitlines()):
        if line_number:
            await page.keyboard.press("Shift+Enter")
        for word_number, word in enumerate(line.split(" ")):
            if word_number:
                await page.keyboard.type(" ", delay=30)
            # A hashtag opens a suggestion list; the following space closes it again, so
            # exactly the typed text stays (Escape would close whole dialogs on some sites).
            await page.keyboard.type(word, delay=35)


def looks_like_login(url: str) -> bool:
    return bool(re.search(r"(accounts\.google\.com|/login|/accounts/login|checkpoint)", url))
