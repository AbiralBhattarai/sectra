from concurrent.futures import ThreadPoolExecutor

import pytest

from src.adapters.output.storage.local_fs_storage_adapter import LocalFsStorageAdapter
from src.application.services.music_library_service import MusicLibraryService
from src.domain.exceptions import AppValidationException, NotFoundException


@pytest.fixture
def library(tmp_path):
    with ThreadPoolExecutor(1) as executor:
        yield MusicLibraryService(LocalFsStorageAdapter(tmp_path, executor))


async def body(*parts: bytes):
    for part in parts:
        yield part


async def test_upload_list_and_resolve(library, tmp_path):
    track = await library.upload("My Chill Beat (final).MP3", body(b"ID3", b"data"))

    assert track.file.endswith("-My-Chill-Beat-final.mp3")
    assert track.name == "My Chill Beat final"
    assert (tmp_path / "music" / track.file).read_bytes() == b"ID3data"
    assert await library.list() == [track]
    assert await library.path(track.file) == tmp_path / "music" / track.file


async def test_rejects_non_audio(library):
    with pytest.raises(AppValidationException, match="Unsupported audio type"):
        await library.upload("virus.exe", body(b"x"))


@pytest.mark.parametrize("file", ["../../etc/passwd", "nope.mp3", "deadbeef-missing.mp3"])
async def test_unknown_or_unsafe_names_are_not_found(library, file):
    with pytest.raises(NotFoundException):
        await library.path(file)


async def test_built_in_tracks_are_listed_first_and_resolvable(tmp_path):
    from src.adapters.output.storage.music_manifest import load_default_tracks

    defaults_dir = tmp_path / "defaults"
    defaults_dir.mkdir()
    (defaults_dir / "manifest.json").write_text(
        '{"tracks": ['
        '{"file": "sectra-a-sunny.mp3", "title": "Sunny", "artist": "A", "mood": "upbeat"},'
        '{"file": "sectra-b-missing.mp3", "title": "Missing", "artist": "B", "mood": "chill"}]}'
    )
    (defaults_dir / "sectra-a-sunny.mp3").write_bytes(b"ID3")

    with ThreadPoolExecutor(1) as executor:
        storage = LocalFsStorageAdapter(tmp_path / "data", executor, defaults_dir)
        library = MusicLibraryService(storage, load_default_tracks(defaults_dir))
        upload = await library.upload("mine.mp3", body(b"x"))
        tracks = await library.list()

        # Missing files are left out; built-ins come before uploads.
        assert [(t.name, t.default, t.mood) for t in tracks] == [
            ("Sunny", True, "upbeat"),
            ("mine", False, None),
        ]
        assert await library.path("sectra-a-sunny.mp3") == defaults_dir / "sectra-a-sunny.mp3"
        assert await library.path(upload.file) == tmp_path / "data" / "music" / upload.file
        with pytest.raises(NotFoundException):
            await library.path("sectra-b-missing.mp3")


def test_bundled_manifest_is_all_cc0_with_unique_files():
    import json
    from pathlib import Path

    manifest = json.loads(
        (Path(__file__).parents[3] / "assets" / "music" / "manifest.json").read_text()
    )
    tracks = manifest["tracks"]
    assert 50 <= len(tracks) <= 100
    assert {t["license"] for t in tracks} == {"CC0-1.0"}
    assert len({t["file"] for t in tracks}) == len(tracks)
    assert all(t["file"].startswith("sectra-") and t["url"].startswith("https://") for t in tracks)
