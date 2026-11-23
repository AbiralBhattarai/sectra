"""poster login <platform> | poster serve | poster run [--dry-run] [--once] [--platform P]
| poster status | poster delete [--platform P] [--check | --yes] [--limit N]"""

import argparse
import asyncio
import json
import logging
import os
import random
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from poster import deleting, outbox
from poster.browser import open_for_login, session
from poster.config import PLATFORMS, Settings, load_settings
from poster.platforms import uploader_for
from poster.platforms.base import ChallengeError, NotLoggedInError, Post, title_from
from poster.schedule import daily_cap_reached, due_at
from poster.video_info import mp4_duration, too_long

logger = logging.getLogger("poster")

#: Even with nothing due, look at the outbox this often for new clips.
_IDLE_POLL = timedelta(minutes=10)
#: `serve` looks for Post-button clips this often.
_SERVE_POLL = timedelta(seconds=5)
#: After a failed post, wait this long (doubling per failure) before trying again.
_RETRY_AFTER = timedelta(minutes=1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="poster", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    login = commands.add_parser("login", help="log in to a platform once, by hand")
    login.add_argument("platform", choices=PLATFORMS)
    run = commands.add_parser("run", help="post the outbox on schedule (until stopped)")
    run.add_argument("--dry-run", action="store_true", help="fill everything in, don't publish")
    run.add_argument("--once", action="store_true", help="one pass, then exit")
    run.add_argument("--platform", action="append", choices=PLATFORMS, help="only these")
    serve = commands.add_parser(
        "serve", help="post clips sent with Sectra's Post button right away (until stopped)"
    )
    serve.add_argument("--dry-run", action="store_true", help="fill everything in, don't publish")
    commands.add_parser("status", help="queue and schedule per platform")
    delete = commands.add_parser(
        "delete",
        help="delete what the poster uploaded (only lists them unless --check or --yes)",
    )
    delete.add_argument("--platform", action="append", choices=deleting.DELETABLE)
    mode = delete.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="find each post and open its delete dialog, then cancel",
    )
    mode.add_argument("--yes", action="store_true", help="really delete (can't be undone)")
    delete.add_argument("--limit", type=int, help="stop after this many posts")
    args = parser.parse_args(argv)

    settings = load_settings()
    _configure_logging(settings)
    if args.command == "login":
        asyncio.run(login_platform(settings, args.platform))
    elif args.command == "serve":
        try:
            asyncio.run(serve_loop(settings, dry_run=args.dry_run))
        except KeyboardInterrupt:
            logger.info("Stopped")
    elif args.command == "run":
        platforms = tuple(args.platform or settings.platforms)
        try:
            asyncio.run(run_loop(settings, platforms, dry_run=args.dry_run, once=args.once))
        except KeyboardInterrupt:
            logger.info("Stopped")
    elif args.command == "delete":
        platforms = tuple(args.platform or deleting.DELETABLE)
        try:
            asyncio.run(delete_posts(settings, platforms, args.check, args.yes, args.limit))
        except KeyboardInterrupt:
            logger.info("Stopped")
    else:
        print_status(settings)


# ---- login --------------------------------------------------------------------------


async def login_platform(settings: Settings, platform: str) -> None:
    uploader = uploader_for(platform, settings)
    print(f"Log in to {platform} in the browser window, then close the window.")
    process = open_for_login(settings, platform, uploader.login_url)
    if process is not None:
        await asyncio.to_thread(process.wait)
    else:
        logger.info("Chrome not found; using Playwright's browser for the login")
        async with session(replace(settings, headless=False), platform) as ctx:
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await page.goto(uploader.login_url)
            await ctx.wait_for_event("close", timeout=0)
    state = _load_state(settings)
    state.setdefault(platform, {})["paused"] = None
    _save_state(settings, state)
    print(f"Saved the {platform} session. Check it with:")
    print(f"  uv run poster run --dry-run --platform {platform}")


# ---- run ----------------------------------------------------------------------------


async def run_loop(
    settings: Settings, platforms: tuple[str, ...], dry_run: bool, once: bool
) -> None:
    rng = random.Random()
    logger.info(
        "Posting %s from %s (%d/day, %02d-%02d h)%s",
        ", ".join(platforms),
        settings.outbox_dir,
        settings.posts_per_day,
        *settings.active_hours,
        " - DRY RUN" if dry_run else "",
    )
    while True:
        state = _load_state(settings)
        now = _now()
        wake = now + _IDLE_POLL
        for platform in platforms:
            entry = state.setdefault(platform, {})
            if entry.get("paused"):
                continue
            items = outbox.scan(settings.outbox_dir)
            item = outbox.next_for(platform, items, settings.max_failures)
            if item is None:
                continue
            if not dry_run:
                due = _due(settings, platform, items, entry, now, rng)
                _save_state(settings, state)
                if due > now:
                    wake = min(wake, due)
                    continue
            outcome = await post_one(settings, platform, item, state, dry_run)
            # Re-plan from this post; after a failure don't hammer the site.
            entry["next_at"] = (
                None if outcome == "posted" else (_now() + 15 * _RETRY_AFTER).isoformat()
            )
            _save_state(settings, state)
            now = _now()
        if once or dry_run:
            return
        pause = max(5.0, (wake - _now()).total_seconds())
        logger.info("Next check at %s", (_now() + timedelta(seconds=pause)).strftime("%H:%M"))
        await asyncio.sleep(pause)


# ---- serve --------------------------------------------------------------------------


async def serve_loop(settings: Settings, dry_run: bool = False) -> None:
    """Post every clip sent with Sectra's Post button to each platform it names, as soon
    as it lands in the outbox, one post at a time. No schedule or daily cap."""
    logger.info(
        "Watching %s for Post clicks (%s)%s",
        settings.outbox_dir,
        ", ".join(settings.platforms),
        " - DRY RUN" if dry_run else "",
    )
    retry_at: dict[tuple[Path, str], datetime] = {}
    tried: set[tuple[Path, str]] = set()  # dry runs: once each
    while True:
        state = _load_state(settings)
        items = outbox.scan(settings.outbox_dir)
        for item, platform in outbox.requested(items, settings.max_failures, settings.platforms):
            key = (item.sidecar, platform)
            if key in tried or retry_at.get(key, _now()) > _now():
                continue
            paused = state.get(platform, {}).get("paused")
            if paused:
                hint = _paused_hint(platform, paused)
                if item.data.get("blocked", {}).get(platform, {}).get("reason") != hint:
                    outbox.record_blocked(item, platform, _now(), hint)
                continue
            outcome = await post_one(settings, platform, item, state, dry_run)
            _save_state(settings, state)
            if dry_run:
                tried.add(key)
            elif outcome == "failed":
                delay = _RETRY_AFTER * 2 ** max(0, item.failures(platform) - 1)
                retry_at[key] = _now() + delay
            elif outcome == "transient":
                retry_at[key] = _now() + _RETRY_AFTER
        await asyncio.sleep(_SERVE_POLL.total_seconds())


def _paused_hint(platform: str, reason: str) -> str:
    return f"{reason} - run: cd poster && uv run poster login {platform}"


def _due(settings, platform, items, entry, now, rng) -> datetime:
    posted = [t.astimezone() for t in outbox.posted_times(platform, items)]
    planned = datetime.fromisoformat(entry["next_at"]) if entry.get("next_at") else None
    due = due_at(
        posted, now, settings.posts_per_day, settings.active_hours, settings.jitter, rng, planned
    )
    entry["next_at"] = due.isoformat()
    return due


async def post_one(
    settings: Settings, platform: str, item: outbox.Item, state: dict, dry_run: bool
) -> str:
    """ "posted", "failed" (counts against the clip), "blocked" (platform paused: log in
    again) or "transient" (browser/site trouble before the upload began; not counted)."""
    uploader = uploader_for(platform, settings)
    post = Post(
        video=item.video,
        caption=item.caption,
        title=title_from(item.caption) or str(item.data.get("title", "")),
    )
    label = f"{platform}: {item.video.parent.name}/{item.video.name}"
    if reason := too_long(mp4_duration(item.video), platform, settings.max_seconds):
        # The site would accept the file and then hang on "Sharing…" forever.
        logger.error("Not posting %s: %s", label, reason)
        if not dry_run:
            outbox.record_failure(
                item, platform, _now(), reason, settings.max_failures, give_up=True
            )
        return "failed"
    logger.info("Posting %s", label)
    try:
        async with session(settings, platform) as context:
            page = context.pages[0] if context.pages else await context.new_page()
            started = False
            try:
                await uploader.check_login(page)
                started = True
                url = await uploader.upload(page, post, dry_run)
                if dry_run:
                    shot = await _screenshot(settings, page, platform, "dry-run")
                    logger.info("Dry run filled in %s; screenshot %s", label, shot)
                    return "posted"
            except (NotLoggedInError, ChallengeError) as exc:
                shot = await _screenshot(settings, page, platform, "paused")
                state.setdefault(platform, {})["paused"] = str(exc)
                if item.post_now:
                    outbox.record_blocked(item, platform, _now(), _paused_hint(platform, str(exc)))
                logger.error(
                    "%s paused: %s (screenshot %s). Fix it, then: uv run poster login %s",
                    platform, exc, shot, platform,
                )  # fmt: skip
                return "blocked"
            except Exception as exc:
                if page.is_closed():
                    # Someone closed the poster's Chrome window (or Chrome quit): not the
                    # clip's fault, so it doesn't count towards MAX_FAILURES.
                    logger.warning(
                        "%s: the browser window was closed mid-post; retrying shortly", label
                    )
                    return "transient"
                shot = await _screenshot(settings, page, platform, "failed")
                if not started:
                    # Site slow or down before anything was uploaded: not the clip's fault.
                    logger.warning("%s unreachable (%s; screenshot %s)", platform, exc, shot)
                    return "transient"
                logger.exception("Posting %s failed (screenshot %s)", label, shot)
                if not dry_run:
                    error = f"{type(exc).__name__}: {exc}"
                    outbox.record_failure(item, platform, _now(), error, settings.max_failures)
                return "failed"
    except Exception:
        # The browser didn't start (profile open elsewhere, Chrome missing): not the clip's fault.
        logger.exception("Couldn't open the %s browser profile", platform)
        return "transient"
    try:
        outbox.record_post(item, platform, _now(), url)
    except OSError:
        # It is live; the record waits in the sidecar's .partial, which scans pick up.
        logger.exception("Posted %s but couldn't update its sidecar", label)
    logger.info("Posted %s%s", label, f" → {url}" if url else "")
    return "posted"


async def _screenshot(settings: Settings, page, platform: str, tag: str) -> Path | None:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    path = settings.logs_dir / f"{_now():%Y%m%d-%H%M%S}-{platform}-{tag}.png"
    try:
        await page.screenshot(path=str(path), full_page=True)
        return path
    except Exception:
        return None


# ---- delete -------------------------------------------------------------------------


async def delete_posts(
    settings: Settings,
    platforms: tuple[str, ...],
    check: bool,
    confirm: bool,
    limit: int | None,
) -> None:
    found = deleting.targets(outbox.scan(settings.outbox_dir), platforms)
    if limit is not None:
        found = found[:limit]
    if not found:
        print("Nothing to delete: no posts recorded in the outbox for", ", ".join(platforms))
        return
    for target in found:
        print(f"  {target.platform:<8} {target.url or '(found by caption)'}  {target.caption[:70]}")
    print(f"{len(found)} post(s).")
    if not (check or confirm):
        print("Nothing deleted. Add --check to test finding them, or --yes to delete them.")
        return

    counts: dict[str, int] = {}
    for platform in platforms:
        mine = [t for t in found if t.platform == platform]
        if not mine:
            continue
        async with session(settings, platform) as context:
            page = context.pages[0] if context.pages else await context.new_page()
            for target in mine:
                try:
                    result = await deleting.delete_one(page, target, confirm=confirm)
                except (NotLoggedInError, ChallengeError) as exc:
                    logger.warning(
                        "%s: %s; skipping the rest (%s)",
                        platform,
                        exc,
                        _paused_hint(platform, str(exc)),
                    )
                    break
                except Exception as exc:
                    shot = await _screenshot(settings, page, platform, "delete")
                    result = deleting.Outcome("skipped", f"{type(exc).__name__}: {exc}"[:200])
                    if shot:
                        result.detail += f" (screenshot {shot})"
                if confirm and result.status in ("deleted", "gone"):
                    deleting.record_deleted(target.item, platform, _now(), result.detail)
                counts[result.status] = counts.get(result.status, 0) + 1
                logger.info(
                    "%s %s: %s %s", platform, result.status, target.caption[:60], result.detail
                )
                # Unhurried, one at a time, like doing it by hand.
                await page.wait_for_timeout(random.randint(3_000, 6_000))
    print("Done:", ", ".join(f"{n} {status}" for status, n in sorted(counts.items())) or "nothing")


# ---- status -------------------------------------------------------------------------


def print_status(settings: Settings) -> None:
    items = outbox.scan(settings.outbox_dir)
    state = _load_state(settings)
    now = _now()
    print(f"Outbox: {settings.outbox_dir} ({len(items)} clips)")
    for platform in settings.platforms:
        posted = [t.astimezone() for t in outbox.posted_times(platform, items)]
        today = sum(1 for t in posted if t.date() == now.date())
        failed = sum(1 for i in items if i.failures(platform) >= settings.max_failures)
        entry = state.get(platform, {})
        if entry.get("paused"):
            when = f"PAUSED: {entry['paused']}"
        elif daily_cap_reached(posted, now, settings.posts_per_day):
            when = "daily cap reached"
        elif entry.get("next_at"):
            when = f"next ≈ {datetime.fromisoformat(entry['next_at']):%a %H:%M}"
        else:
            when = "next: when `poster run` starts"
        pending = outbox.pending(platform, items, settings.max_failures)
        print(
            f"  {platform:<10} today {today}/{settings.posts_per_day}  "
            f"waiting {pending}  gave up {failed}  {when}"
        )


# ---- helpers ------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now().astimezone()


def _load_state(settings: Settings) -> dict:
    try:
        return json.loads(settings.state_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(settings: Settings, state: dict) -> None:
    partial = settings.state_file.with_suffix(".partial")
    partial.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(partial, settings.state_file)


def _configure_logging(settings: Settings) -> None:
    settings.logs_dir.mkdir(parents=True, exist_ok=True)
    # Captions carry emoji; a Windows console's code page can't print them.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    file = logging.FileHandler(settings.logs_dir / "poster.log", encoding="utf-8")
    for handler in (console, file):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


if __name__ == "__main__":
    main()
