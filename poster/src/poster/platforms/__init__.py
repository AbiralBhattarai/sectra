from poster.config import Settings
from poster.platforms.base import Uploader
from poster.platforms.facebook import FacebookUploader
from poster.platforms.instagram import InstagramUploader
from poster.platforms.tiktok import TikTokUploader
from poster.platforms.x import XUploader
from poster.platforms.youtube import YouTubeUploader


def uploader_for(platform: str, settings: Settings) -> Uploader:
    if platform == "youtube":
        return YouTubeUploader(settings.youtube_visibility)
    if platform == "tiktok":
        return TikTokUploader()
    if platform == "instagram":
        return InstagramUploader()
    if platform == "x":
        return XUploader()
    if platform == "facebook":
        return FacebookUploader()
    raise ValueError(f"Unknown platform {platform}")
