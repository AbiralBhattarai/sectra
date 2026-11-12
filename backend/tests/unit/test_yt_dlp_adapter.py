import pytest

from src.adapters.output.downloader.yt_dlp_adapter import live_problem


@pytest.mark.parametrize(
    ("info", "message"),
    [
        ({"live_status": "is_live"}, "live stream"),
        ({"is_live": True}, "live stream"),
        ({"live_status": "is_upcoming"}, "hasn't started"),
        ({"live_status": "post_live"}, "still processing"),
    ],
)
def test_live_streams_are_refused_instead_of_recorded_forever(info, message):
    assert message in live_problem(info)


@pytest.mark.parametrize("status", ["not_live", "was_live", None])
def test_recordings_download(status):
    assert live_problem({"live_status": status}) is None
