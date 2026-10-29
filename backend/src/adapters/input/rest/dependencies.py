from fastapi import Request

from src.ports.input.clip_editing_port import ClipEditingPort
from src.ports.input.clip_export_port import ClipExportPort
from src.ports.input.job_management_port import JobManagementPort
from src.ports.input.music_library_port import MusicLibraryPort
from src.ports.input.video_library_port import VideoLibraryPort


def get_job_service(request: Request) -> JobManagementPort:
    return request.app.state.container.job_service


def get_video_library(request: Request) -> VideoLibraryPort:
    return request.app.state.container.video_library


def get_clip_editing(request: Request) -> ClipEditingPort:
    return request.app.state.container.clip_editing


def get_music_library(request: Request) -> MusicLibraryPort:
    return request.app.state.container.music_library


def get_clip_export(request: Request) -> ClipExportPort:
    return request.app.state.container.clip_export
