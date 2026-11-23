"""`poster delete`: take down what the poster uploaded, found through the outbox sidecars.

Only clips a sidecar records as posted are touched; anything uploaded by hand is never
looked at. YouTube and X posts are found by the link saved when they were posted. TikTok
saves no link, so a post is looked up in TikTok Studio by its caption and skipped unless
exactly one post matches.

Three levels: list (default, no browser), ``check`` (open each post and its delete
dialog, then cancel) and ``confirm`` (delete). A deleted post is written to the sidecar
under ``deleted``; ``posted`` stays, so the scheduler never uploads the clip again."""

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from playwright.async_api import Locator, Page
from playwright.async_api import TimeoutError as PlaywrightTimeout

from poster.outbox import Item
from poster.platforms.base import ChallengeError, NotLoggedInError, looks_like_login

logger = logging.getLogger("poster")

#: Platforms `poster delete` knows how to delete from.
DELETABLE = ("youtube", "tiktok", "x")


@dataclass
class Target:
    item: Item
    platform: str
    url: str | None

    @property
    def caption(self) -> str:
        return self.item.caption


@dataclass
class Outcome:
    #: deleted | gone (already not there) | checked (dialog found, cancelled) | skipped
    status: str
    detail: str = ""


def targets(items: list[Item], platforms: tuple[str, ...]) -> list[Target]:
    """Every (clip, platform) the poster posted and hasn't deleted yet."""
    found = []
    for item in items:
        posted = item.data.get("posted", {})
        deleted = item.data.get("deleted", {})
        for platform in platforms:
            entry = posted.get(platform)
            if entry is not None and platform not in deleted:
                found.append(Target(item, platform, entry.get("url")))
    return found


_YOUTUBE_ID = re.compile(r"(?:shorts/|[?&]v=|youtu\.be/|/video/)([\w-]{11})")
_X_STATUS = re.compile(r"/status/(\d+)")


def youtube_id(url: str | None) -> str | None:
    match = _YOUTUBE_ID.search(url or "")
    return match.group(1) if match else None


def x_status_id(url: str | None) -> str | None:
    match = _X_STATUS.search(url or "")
    return match.group(1) if match else None


#: How much of a caption has to match on TikTok (lists cut long captions short).
CAPTION_KEY_CHARS = 40


def normalize(text: str) -> str:
    """Lower case, letters/digits/spaces only, single spaces. Mirrors ``_NORMALIZE_JS``."""
    return " ".join(re.sub(r"[^\w ]+", " ", text.casefold()).split())


def caption_key(caption: str) -> str:
    """The start of a caption as TikTok shows it, normalized, for finding the post."""
    return normalize(caption)[:CAPTION_KEY_CHARS].strip()


def record_deleted(item: Item, platform: str, at: datetime, note: str = "") -> None:
    from poster.outbox import _update  # the sidecar's atomic read-change-write

    def change(data: dict) -> None:
        entry = {"at": at.isoformat()}
        if note:
            entry["note"] = note
        data.setdefault("deleted", {})[platform] = entry

    _update(item, change)


async def delete_one(page: Page, target: Target, confirm: bool) -> Outcome:
    if target.platform == "youtube":
        return await _youtube(page, target, confirm)
    if target.platform == "x":
        return await _x(page, target, confirm)
    if target.platform == "tiktok":
        return await _tiktok(page, target, confirm)
    return Outcome("skipped", f"deleting from {target.platform} isn't supported")


# ---- YouTube ---------------------------------------------------------------------------

STUDIO_VIDEO = "https://studio.youtube.com/video/{id}/edit"
# The details page's "⋮" menu holds "Delete forever"; the dialog wants a checkbox ticked.
YT_MENU_BUTTONS = (
    "ytcp-video-details-section ytcp-icon-button, ytcp-icon-button[aria-label], button[aria-label]"
)
YT_MENU_LABEL = re.compile(r"option|more|action", re.I)
YT_DELETE = re.compile(r"delete forever", re.I)
YT_DIALOG = "ytcp-confirmation-dialog, tp-yt-paper-dialog, [role='dialog']"
YT_GONE = re.compile(r"(doesn.t exist|not found|was deleted|can.t find|couldn.t find)", re.I)


async def _youtube(page: Page, target: Target, confirm: bool) -> Outcome:
    video_id = youtube_id(target.url)
    if video_id is None:
        return Outcome("skipped", f"no video id in the saved link {target.url!r}")
    await page.goto(STUDIO_VIDEO.format(id=video_id), wait_until="domcontentloaded")
    await page.wait_for_timeout(5_000)
    if looks_like_login(page.url):
        raise NotLoggedInError("YouTube redirected to log in")
    if video_id not in page.url or await page.get_by_text(YT_GONE).count():
        return Outcome("gone", "Studio no longer has this video")

    item = await _open_menu_with(page, page.locator(YT_MENU_BUTTONS), YT_MENU_LABEL, YT_DELETE)
    if item is None:
        return Outcome("skipped", "couldn't find 'Delete forever' in the video's menu")
    await item.click()
    dialog = page.locator(YT_DIALOG).filter(has_text=YT_DELETE).last
    await dialog.wait_for(state="visible", timeout=15_000)
    await dialog.get_by_role("checkbox").first.click()
    if not confirm:
        await _cancel(page, dialog)
        return Outcome("checked")
    await dialog.get_by_role("button", name=YT_DELETE).last.click()
    await dialog.wait_for(state="hidden", timeout=60_000)
    return Outcome("deleted")


# ---- X ---------------------------------------------------------------------------------

X_CARET = '[data-testid="caret"]'
X_CONFIRM = '[data-testid="confirmationSheetConfirm"]'
X_GONE = re.compile(r"(doesn.t exist|post is unavailable|this page doesn.t exist|deleted)", re.I)


async def _x(page: Page, target: Target, confirm: bool) -> Outcome:
    status_id = x_status_id(target.url)
    if status_id is None:
        return Outcome("skipped", f"no post id in the saved link {target.url!r}")
    await page.goto(target.url, wait_until="domcontentloaded")
    await page.wait_for_timeout(3_000)
    if looks_like_login(page.url) or "/i/flow/login" in page.url:
        raise NotLoggedInError("X redirected to log in")
    # The post's own permalink is the link around its timestamp (replies link theirs).
    post = page.locator(f'article[data-testid="tweet"]:has(a[href$="/status/{status_id}"] time)')
    try:
        await post.first.wait_for(state="visible", timeout=20_000)
    except PlaywrightTimeout:
        if await page.get_by_text(X_GONE).count():
            return Outcome("gone", "X says the post doesn't exist")
        return Outcome("skipped", "the post didn't load")
    await post.first.locator(X_CARET).first.click()
    delete = page.get_by_role("menuitem").filter(has_text=re.compile(r"^\s*Delete\s*$", re.I))
    try:
        await delete.first.wait_for(state="visible", timeout=10_000)
    except PlaywrightTimeout:
        await page.keyboard.press("Escape")
        return Outcome("skipped", "no Delete in the post's menu (not this account's post?)")
    if not confirm:
        await page.keyboard.press("Escape")
        return Outcome("checked")
    await delete.first.click()
    await page.locator(X_CONFIRM).first.click(timeout=10_000)
    await post.first.wait_for(state="detached", timeout=30_000)
    return Outcome("deleted")


# ---- TikTok ----------------------------------------------------------------------------

STUDIO_CONTENT = "https://www.tiktok.com/tiktokstudio/content"
TT_CAPTCHA = "#captcha-verify-container, .captcha_verify_container"
TT_SEARCH = re.compile(r"search", re.I)
TT_DELETE = re.compile(r"^\s*delete\s*$", re.I)
#: A post row holds its own action buttons (privacy, edit, stats, comments, "⋯").
TT_ROW_MIN_BUTTONS = 3

_NORMALIZE_JS = (
    "s => s.toLowerCase().replace(/[^\p{L}\p{N}_ ]+/gu, ' ').replace(/\s+/g, ' ').trim()"
)

#: Marks the visible rows showing this post and returns how many there are. A hit is a
#: visible element whose text reads as the post (at least its title, at most its full
#: caption); its row is the smallest ancestor holding the row's action buttons.
_FIND_ROWS_JS = f"""([title, caption, minButtons]) => {{
  const norm = {_NORMALIZE_JS};
  const shows = el => {{
    const t = norm(el.innerText || '');
    return t.length > 0 && t.startsWith(title) && caption.startsWith(t);
  }};
  const visible = el => el.getClientRects().length > 0;
  document.querySelectorAll('[data-sectra-row]').forEach(e => e.removeAttribute('data-sectra-row'));
  const rows = new Set();
  for (const el of document.querySelectorAll('body *')) {{
    if (!visible(el) || !shows(el) || [...el.children].some(shows)) continue;
    let row = el;
    while (row && row.querySelectorAll('button,[role=button]').length < minButtons) {{
      row = row.parentElement;
    }}
    if (row && row !== document.body) rows.add(row);
  }}
  let i = 0;
  for (const row of rows) row.setAttribute('data-sectra-row', String(i++));
  return rows.size;
}}"""


def tiktok_title(caption: str) -> str:
    """What TikTok Studio lists for a post: the caption before its hashtags."""
    return caption.split("#", 1)[0].strip() or caption.strip()


async def _tiktok(page: Page, target: Target, confirm: bool) -> Outcome:
    title = tiktok_title(target.caption)
    if len(normalize(title)) < 6:
        return Outcome("skipped", "caption too short to find the post safely")
    if STUDIO_CONTENT not in page.url:
        await page.goto(STUDIO_CONTENT, wait_until="domcontentloaded")
        await page.wait_for_timeout(6_000)
    if looks_like_login(page.url):
        raise NotLoggedInError("TikTok redirected to log in")
    if await page.locator(TT_CAPTCHA).count():
        raise ChallengeError("TikTok is showing a captcha")

    count = await _search(page, title, target.caption)
    # Not finding a post is never proof it's gone (search and lists lag), so it's skipped
    # and stays in the queue rather than being recorded as deleted.
    if count == 0:
        return Outcome("skipped", f"no post titled {title!r} in TikTok Studio's search")
    if count > 1:
        return Outcome("skipped", f"{count} posts are titled {title!r}; not guessing")
    row = page.locator('[data-sectra-row="0"]')
    await row.hover()
    # The row's last button is its "⋯" menu (privacy/edit/stats/comments come first).
    more = row.locator("button, [role='button']").last
    await more.click()
    item = page.get_by_text(TT_DELETE).locator("visible=true")
    try:
        await item.first.wait_for(state="visible", timeout=8_000)
    except PlaywrightTimeout:
        await page.keyboard.press("Escape")
        return Outcome("skipped", "the post's ⋯ menu has no Delete")
    await item.first.click()
    dialog = page.locator("[role='dialog'], [class*='modal' i]").filter(has_text=TT_DELETE).last
    await dialog.wait_for(state="visible", timeout=15_000)
    if not confirm:
        await _cancel(page, dialog)
        return Outcome("checked")
    await dialog.get_by_role("button", name=TT_DELETE).last.click()
    await dialog.wait_for(state="hidden", timeout=30_000)
    await page.wait_for_timeout(3_000)
    if await _search(page, title, target.caption):
        return Outcome("skipped", "TikTok still lists the post after deleting")
    return Outcome("deleted")


async def _search(page: Page, title: str, caption: str) -> int:
    """Search Studio's posts for ``title``; returns how many matching rows show."""
    box = page.get_by_placeholder(TT_SEARCH).first
    await box.fill("")
    await box.fill(title)
    await box.press("Enter")
    await page.wait_for_timeout(4_000)
    args = [normalize(title), normalize(caption), TT_ROW_MIN_BUTTONS]
    return await page.evaluate(_FIND_ROWS_JS, args)


# ---- shared ----------------------------------------------------------------------------


async def _open_menu_with(
    page: Page, buttons: Locator, label: re.Pattern, wanted: re.Pattern, any_label: bool = False
) -> Locator | None:
    """Open menu buttons one by one until a menu shows an item matching ``wanted``.

    Buttons whose label matches ``label`` are tried first; with ``any_label`` the
    unlabelled ones follow (TikTok's icon buttons often have none)."""
    labelled, unlabelled = [], []
    for index in range(min(await buttons.count(), 30)):
        button = buttons.nth(index)
        if not await button.is_visible():
            continue
        text = " ".join(
            filter(None, [await button.get_attribute("aria-label"), await button.inner_text()])
        )
        if wanted.search(text):
            return button  # a direct Delete button
        if label.search(text):
            labelled.append(button)
        elif any_label and not text.strip():
            unlabelled.append(button)
    for button in labelled + unlabelled:
        await button.click()
        item = page.get_by_role("menuitem").filter(has_text=wanted)
        item = item.or_(page.locator("[role='menu'] *, [role='listbox'] *").filter(has_text=wanted))
        try:
            await item.first.wait_for(state="visible", timeout=3_000)
            return item.first
        except PlaywrightTimeout:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(300)
    return None


async def _cancel(page: Page, dialog: Locator) -> None:
    cancel = dialog.get_by_role("button", name=re.compile(r"cancel", re.I))
    if await cancel.count():
        await cancel.first.click()
    else:
        await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)
