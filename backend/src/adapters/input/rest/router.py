from fastapi import APIRouter

from src.adapters.input.rest import clips, events, exports, health, jobs, music, videos


def build_router() -> APIRouter:
    router = APIRouter()
    router.include_router(health.router)
    router.include_router(jobs.router)
    router.include_router(events.router)
    router.include_router(videos.router)
    router.include_router(clips.router)
    router.include_router(music.router)
    router.include_router(exports.router)
    return router
