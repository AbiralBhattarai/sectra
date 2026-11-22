"""Instagram Reels through instagram.com's "New post" dialog (videos are shared as reels).

The dialog (checked 2026-11-22): Create → menu (Post / Live video / Ad) → file picker →
Crop → Edit → New reel (caption, Share)."""

import re

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

HOME = "https://www.instagram.com/"
# Selectors (aria labels and visible text).
NEW_POST = ('svg[aria-label="New post"]', 'svg[aria-label="Create"]')
# The Create menu's items are plain <span>s now (no role); older layouts used links.
POST_MENU_ITEM = "Post"
DIALOG = 'div[role="dialog"]'
FILE_INPUT = 'input[type="file"]'
REELS_NOTICE_OK = "OK"  # "Video posts are now shared as reels"
CROP_BUTTON = 'svg[aria-label="Select crop" i]'  # "Select Crop" today
CROP_ORIGINAL = "Original"
NEXT = "Next"
# role=textbox aria-label="Add a caption..." today; "Write a caption..." before.
CAPTION_BOX = (
    'div[role="textbox"][aria-label*="caption" i]',
    'div[contenteditable="true"][aria-label*="caption" i]',
)
CAPTION_STEP = "New reel"  # the dialog heading once the caption page is up
SHARE = "Share"
SHARED = re.compile(r"(reel|post) (has been )?shared", re.IGNORECASE)
LOGIN_FORM = 'input[name="username"]'


class InstagramUploader:
    name = "instagram"
    login_url = "https://www.instagram.com/accounts/login/"

    async def check_login(self, page: Page) -> None:
        await page.goto(HOME, wait_until="domcontentloaded")
        await page.wait_for_timeout(3_000)
        if looks_like_login(page.url) or await page.locator(LOGIN_FORM).count():
            raise NotLoggedInError("Instagram shows the login form")
        if "challenge" in page.url:
            raise ChallengeError("Instagram wants the account verified")

    async def upload(self, page: Page, post: Post, dry_run: bool) -> str | None:
        new_post = await first_visible(*(page.locator(s) for s in NEW_POST))
        await new_post.click()
        dialog = page.locator(DIALOG).last
        # Newer layouts open a Post / Live video / Ad menu first; older ones go straight
        # to the dialog. Only visible matches: "Post" also appears in hidden svg titles.
        menu_item = (
            page.get_by_role("link", name=POST_MENU_ITEM, exact=True)
            .or_(page.get_by_text(POST_MENU_ITEM, exact=True))
            .filter(visible=True)
        )
        await first_visible(menu_item, dialog.locator(FILE_INPUT))
        if not await dialog.locator(FILE_INPUT).count():
            await menu_item.first.click()
        await dialog.locator(FILE_INPUT).first.set_input_files(post.video, timeout=60_000)
        await maybe_click(
            page.get_by_role("button", name=REELS_NOTICE_OK, exact=True), timeout=5_000
        )

        # Keep the clip 9:16 instead of Instagram's default square crop.
        if await maybe_click(dialog.locator(CROP_BUTTON), timeout=15_000):
            await maybe_click(dialog.get_by_text(CROP_ORIGINAL, exact=True))
        for _ in range(2):  # crop → edit → caption
            await dialog.get_by_role("button", name=NEXT, exact=True).first.click(timeout=60_000)
            await page.wait_for_timeout(1_500)

        await dialog.get_by_role("heading", name=CAPTION_STEP).wait_for(timeout=60_000)
        caption = await first_visible(*(dialog.locator(s) for s in CAPTION_BOX), timeout=60_000)
        await replace_text(page, caption, post.caption)
        await page.keyboard.type(" ")  # closes the last hashtag's suggestion list
        await page.wait_for_timeout(500)
        if dry_run:
            return None
        await dialog.get_by_role("button", name=SHARE, exact=True).first.click()
        await page.get_by_text(SHARED).first.wait_for(timeout=UPLOAD_TIMEOUT_MS)
        return None
