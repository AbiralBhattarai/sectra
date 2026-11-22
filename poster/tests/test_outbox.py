import json
from datetime import datetime

from poster import outbox
from poster.platforms.base import title_from


def clip(folder, rank, created, caption="Wait for it #fyp", **extra):
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"{rank:02d} {caption.replace('?', '')}"
    (folder / f"{stem}.mp4").write_bytes(b"mp4")
    data = {"caption": caption, "rank": rank, "created_at": created, "posted": {}, "failures": {}}
    (folder / f"{stem}.json").write_text(json.dumps(data | extra), encoding="utf-8")
    return folder / f"{stem}.json"


def test_scan_orders_oldest_video_first_then_rank(tmp_path):
    clip(tmp_path / "newer [b]", 1, "2026-11-20T12:00:00")
    clip(tmp_path / "older [a]", 2, "2026-11-19T10:00:00", caption="second")
    clip(tmp_path / "older [a]", 1, "2026-11-19T10:00:00", caption="first")
    (tmp_path / "older [a]" / "03 orphan.json").write_text("{}")  # no video: ignored
    (tmp_path / "older [a]" / "04 half.mp4").write_bytes(b"")  # no sidecar yet: ignored

    items = outbox.scan(tmp_path)

    assert [(i.video.parent.name, i.rank) for i in items] == [
        ("older [a]", 1),
        ("older [a]", 2),
        ("newer [b]", 1),
    ]


def test_posting_and_failures_are_recorded_in_the_sidecar(tmp_path):
    sidecar = clip(tmp_path / "v", 1, "2026-11-19T10:00:00", caption="He said WHAT? #podcast")
    clip(tmp_path / "v", 2, "2026-11-19T10:00:00", caption="next one")
    [first, second] = outbox.scan(tmp_path)
    assert first.caption == "He said WHAT? #podcast"  # exact, unlike the file name

    when = datetime(2026, 11, 20, 10, 0).astimezone()
    outbox.record_post(first, "tiktok", when, None)
    for _ in range(3):
        outbox.record_failure(second, "tiktok", when, "TimeoutError: no Post button")

    reread = outbox.scan(tmp_path)
    assert json.loads(sidecar.read_text("utf-8"))["posted"]["tiktok"]["at"] == when.isoformat()
    assert reread[0].posted_on("tiktok") and not reread[0].posted_on("youtube")
    assert reread[1].failures("tiktok") == 3
    assert outbox.next_for("tiktok", reread, max_failures=3) is None
    assert outbox.next_for("youtube", reread, max_failures=3).rank == 1
    assert outbox.posted_times("tiktok", reread) == [when]


def test_a_sidecar_locked_for_a_moment_is_retried(tmp_path, monkeypatch):
    # Windows: replacing a file another process has open fails with "Access is denied".
    clip(tmp_path / "v", 1, "2026-11-19T10:00:00")
    [item] = outbox.scan(tmp_path)
    real_replace, calls = outbox.os.replace, []

    def locked_twice(src, dst):
        calls.append(dst)
        if len(calls) <= 2:
            raise PermissionError(5, "Access is denied")
        real_replace(src, dst)

    monkeypatch.setattr(outbox.os, "replace", locked_twice)
    monkeypatch.setattr(outbox.time, "sleep", lambda _: None)
    outbox.record_post(item, "tiktok", datetime(2026, 11, 20).astimezone(), None)

    assert len(calls) == 3
    assert outbox.scan(tmp_path)[0].posted_on("tiktok")
    assert not list((tmp_path / "v").glob("*.partial"))


def test_a_leftover_partial_is_adopted_so_nothing_is_posted_twice(tmp_path):
    sidecar = clip(tmp_path / "v", 1, "2026-11-19T10:00:00")
    newer = json.loads(sidecar.read_text("utf-8"))
    newer["posted"] = {"tiktok": {"at": "2026-11-20T10:00:00+00:00", "url": None}}
    partial = sidecar.with_name(sidecar.name + ".partial")
    partial.write_text(json.dumps(newer), encoding="utf-8")

    [item] = outbox.scan(tmp_path)

    assert item.posted_on("tiktok")
    assert json.loads(sidecar.read_text("utf-8"))["posted"] == newer["posted"]
    assert not partial.exists()


def test_a_cut_short_partial_is_ignored(tmp_path):
    sidecar = clip(tmp_path / "v", 1, "2026-11-19T10:00:00")
    sidecar.with_name(sidecar.name + ".partial").write_text('{"posted": {"tik', encoding="utf-8")

    [item] = outbox.scan(tmp_path)

    assert not item.posted_on("tiktok")


def test_youtube_title_is_the_first_line_without_hashtags():
    assert title_from("He said WHAT?! #podcast #fyp\nmore text") == "He said WHAT?!"
    assert title_from("#only #tags") == "#only #tags"
    assert len(title_from("word " * 50)) <= 100


def test_post_button_clips_go_to_serve_not_the_schedule(tmp_path):
    clip(tmp_path / "v", 1, "2026-11-19T10:00:00", caption="scheduled")
    clip(
        tmp_path / "v",
        0,
        "2026-11-19T10:00:00",
        caption="Hook line #fyp",
        post_now=True,
        description="The clip title",
        platforms=["youtube", "x"],
    )
    items = outbox.scan(tmp_path)

    assert outbox.next_for("tiktok", items, 3).caption == "scheduled"
    assert outbox.pending("youtube", items, 3) == 1
    asked = outbox.requested(items, 3, ("youtube", "tiktok", "instagram", "x"))
    assert [(i.caption, p) for i, p in asked] == [
        ("The clip title", "youtube"),  # the description wins over the caption
        ("The clip title", "x"),
    ]


def test_blocked_and_given_up_are_recorded(tmp_path):
    clip(tmp_path / "v", 0, "2026-11-19T10:00:00", post_now=True, platforms=["x"])
    [item] = outbox.scan(tmp_path)
    when = datetime(2026, 11, 20, 10, 0).astimezone()

    outbox.record_blocked(item, "x", when, "X redirected to log in")
    assert item.data["blocked"]["x"]["reason"] == "X redirected to log in"
    outbox.record_failure(item, "x", when, "boom", max_failures=1)
    assert item.data["failures"]["x"]["gave_up"] is True
    assert outbox.requested([item], 1, ("x",)) == []
    outbox.record_post(item, "x", when, None)
    assert "x" not in item.data["blocked"]


def test_x_text_is_cut_at_a_word():
    from poster.platforms.x import fit_text

    assert fit_text("short") == "short"
    long = "word " * 80
    cut = fit_text(long)
    assert len(cut) <= 280 and cut.endswith("word…")
