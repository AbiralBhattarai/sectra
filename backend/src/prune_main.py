"""Remove what deleted videos left behind: ``data/videos/<id>/`` folders and outbox
folders of videos that no longer exist (deletes made before the worker stopped running
jobs of deleted videos, or while a file was open).

    docker compose exec api python -m src.prune_main          # list only
    docker compose exec api python -m src.prune_main --yes    # delete them
"""

import argparse
import asyncio
import shutil

from src.config.container import build_container
from src.config.settings import get_settings


def _size(path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


async def main(confirm: bool) -> None:
    container = build_container(get_settings())
    try:
        known = {str(video.id) for video in await container.videos.list()}
        leftovers = container.storage.leftovers(known)
        total = 0
        for path in leftovers:
            size = _size(path)
            total += size
            print(f"{size / 1e9:8.2f} GB  {path}")
        print(f"{len(leftovers)} leftover folder(s), {total / 1e9:.2f} GB.")
        if not confirm:
            if leftovers:
                print("Nothing deleted. Add --yes to delete them.")
            return
        for path in leftovers:
            shutil.rmtree(path, ignore_errors=True)
            print(("could not fully remove " if path.exists() else "removed ") + str(path))
    finally:
        await container.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yes", action="store_true", help="really delete")
    asyncio.run(main(parser.parse_args().yes))
