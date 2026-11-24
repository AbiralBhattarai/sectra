import json
from datetime import datetime

from test_outbox import clip

from poster import deleting, outbox

POSTED = {
    "youtube": {"at": "2026-11-22T21:14:42+05:45", "url": "https://youtube.com/shorts/pazNGRmbl-g"},
    "tiktok": {"at": "2026-11-22T21:15:21+05:45", "url": None},
    "x": {"at": "2026-11-22T21:16:39+05:45", "url": "https://x.com/me/status/2124526212412490149"},
}


def test_targets_are_only_what_the_poster_posted_and_not_yet_deleted(tmp_path):
    clip(tmp_path / "v", 1, "2026-11-19T10:00:00", caption="posted", posted=POSTED)
    clip(tmp_path / "v", 2, "2026-11-19T10:00:00", caption="never posted")
    clip(
        tmp_path / "v",
        3,
        "2026-11-19T10:00:00",
        caption="half deleted",
        posted=POSTED,
        deleted={"youtube": {"at": "2026-11-23T10:00:00"}},
    )

    found = deleting.targets(outbox.scan(tmp_path), ("youtube", "tiktok", "x"))

    assert [(t.caption, t.platform) for t in found] == [
        ("posted", "youtube"),
        ("posted", "tiktok"),
        ("posted", "x"),
        ("half deleted", "tiktok"),
        ("half deleted", "x"),
    ]
    assert found[0].url == "https://youtube.com/shorts/pazNGRmbl-g"
    assert deleting.targets(outbox.scan(tmp_path), ("x",))[0].platform == "x"


def test_ids_come_from_the_saved_links():
    assert deleting.youtube_id("https://youtube.com/shorts/pazNGRmbl-g") == "pazNGRmbl-g"
    assert deleting.youtube_id("https://www.youtube.com/watch?v=_stXm5Iwxkc&t=3") == "_stXm5Iwxkc"
    assert deleting.youtube_id("https://youtu.be/_stXm5Iwxkc") == "_stXm5Iwxkc"
    assert deleting.youtube_id(None) is None
    assert deleting.x_status_id("https://x.com/me/status/2124526212412490149") == (
        "2124526212412490149"
    )
    assert deleting.x_status_id("https://x.com/me") is None


def test_caption_key_ignores_case_emoji_and_punctuation():
    key = deleting.caption_key("3 hot sauces 3x the PAIN! 🤢 #GTA6 #HotSauceChallenge #Rockstar")
    assert key == "3 hot sauces 3x the pain gta6 hotsaucech"
    assert len(key) <= deleting.CAPTION_KEY_CHARS


def test_a_deleted_post_is_recorded_and_never_reposted(tmp_path):
    sidecar = clip(tmp_path / "v", 1, "2026-11-19T10:00:00", caption="posted", posted=POSTED)
    [item] = outbox.scan(tmp_path)

    deleting.record_deleted(item, "x", datetime(2026, 11, 23, 12, 0).astimezone(), "gone")

    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["deleted"]["x"]["note"] == "gone"
    assert "x" in data["posted"]  # kept, so the scheduler doesn't upload it again
    [item] = outbox.scan(tmp_path)
    assert not outbox.is_open(item, "x", max_failures=3)
    assert [t.platform for t in deleting.targets([item], ("youtube", "x"))] == ["youtube"]


def test_tiktok_lists_a_post_by_its_caption_before_the_hashtags():
    assert deleting.tiktok_title("51 Hours of Work #Dylan #gta") == "51 Hours of Work"
    assert deleting.tiktok_title("#only #tags") == "#only #tags"
