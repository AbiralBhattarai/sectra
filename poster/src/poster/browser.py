"""Browser sessions: one persistent profile per platform under ``profiles/``, so each
login (done by hand, once) is reused by every later upload."""

import contextlib
import os
import shutil
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from playwright.async_api import BrowserContext, async_playwright

from poster.config import Settings

_CHROME_CANDIDATES = [
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
    / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/google-chrome-stable"),
]


def profile_dir(settings: Settings, platform: str) -> Path:
    path = settings.profiles_dir / platform
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_chrome(settings: Settings) -> Path | None:
    if settings.chrome_path:
        return settings.chrome_path if settings.chrome_path.is_file() else None
    for candidate in _CHROME_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("google-chrome") or shutil.which("chrome")
    return Path(found) if found else None


def open_for_login(settings: Settings, platform: str, url: str) -> subprocess.Popen | None:
    """Open the platform's profile in plain Chrome (not driven by Playwright) for a
    normal, by-hand login. None when Chrome isn't installed."""
    chrome = find_chrome(settings)
    if chrome is None:
        return None
    return subprocess.Popen(
        [
            str(chrome),
            f"--user-data-dir={profile_dir(settings, platform)}",
            "--no-first-run",
            "--no-default-browser-check",
            url,
        ]
    )


@asynccontextmanager
async def session(settings: Settings, platform: str):
    """A browser context on the platform's profile, closed afterwards."""
    async with async_playwright() as playwright:
        options = {
            "headless": settings.headless,
            "viewport": {"width": 1366, "height": 900},
            "accept_downloads": False,
        }
        if settings.browser_channel != "chromium":
            options["channel"] = settings.browser_channel
        context: BrowserContext = await playwright.chromium.launch_persistent_context(
            str(profile_dir(settings, platform)), **options
        )
        context.set_default_timeout(30_000)
        try:
            yield context
        finally:
            with contextlib.suppress(Exception):  # already gone if the window was closed
                await context.close()
