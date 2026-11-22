from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import FileResponse

from src.adapters.input.rest.dependencies import get_stories
from src.application.dto.story import CreateStoryRequest
from src.application.dto.video import VideoDTO
from src.ports.input.story_port import StoryPort

router = APIRouter(tags=["stories"])

Stories = Annotated[StoryPort, Depends(get_stories)]


@router.post("/api/stories", status_code=status.HTTP_202_ACCEPTED)
async def create_story(body: CreateStoryRequest, stories: Stories) -> VideoDTO:
    """Narrate a story: the worker writes the narration, builds the video, transcribes it
    and splits it into postable parts. It is listed with the videos (``kind: story``)."""
    return VideoDTO.from_domain(await stories.create(body.to_spec()), None)


@router.get("/api/stories/options")
async def story_options(stories: Stories) -> dict:
    return stories.options()


@router.get("/api/characters/{name}/{layer:path}")
async def character_layer(name: str, layer: str, stories: Stories) -> FileResponse:
    return FileResponse(
        await stories.character_layer(name, layer),
        media_type="image/svg+xml",
        headers={"Cache-Control": "max-age=3600"},
    )
