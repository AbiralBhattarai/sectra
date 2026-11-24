import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from src.adapters.input.worker.redis_stream_consumer import RedisStreamConsumer
from src.adapters.output.downloader.yt_dlp_adapter import YtDlpAdapter
from src.adapters.output.face.onnx_face_tracker_adapter import OnnxFaceTrackerAdapter
from src.adapters.output.lipsync.rhubarb_adapter import RhubarbLipSyncAdapter
from src.adapters.output.llm.anthropic_adapter import AnthropicLLMAdapter
from src.adapters.output.llm.openai_compat_adapter import OpenAICompatLLMAdapter
from src.adapters.output.media.ffmpeg_media_adapter import FfmpegMediaAdapter
from src.adapters.output.renderer.ffmpeg_renderer_adapter import FfmpegRendererAdapter
from src.adapters.output.stt.faster_whisper_adapter import FasterWhisperAdapter
from src.adapters.output.stt.openai_compat_stt_adapter import OpenAICompatSTTAdapter
from src.adapters.output.tts.kokoro_onnx_adapter import KokoroOnnxAdapter
from src.adapters.output.vad.silero_onnx_adapter import SileroOnnxAdapter
from src.application.services.background_library_service import BackgroundLibraryService
from src.application.services.clip_export_service import ClipExportService
from src.application.services.clip_tracking_service import ClipTrackingService
from src.application.services.highlight_analysis_service import HighlightAnalysisService
from src.application.services.ingest_service import IngestService
from src.application.services.media_preparation_service import MediaPreparationService
from src.application.services.ping_service import PingService
from src.application.services.pipeline_dispatcher import PipelineDispatcher
from src.application.services.speech_detection_service import SpeechDetectionService
from src.application.services.story_clip_service import AnalysisRouter, StoryClipService
from src.application.services.story_composition_service import StoryCompositionService
from src.application.services.story_narration_service import StoryNarrationService
from src.application.services.transcription_service import TranscriptionService
from src.config.container import Container, build_container
from src.config.settings import Settings
from src.domain.enums.job_type_enum import JobType
from src.ports.output.llm_port import LLMPort
from src.ports.output.stt_port import STTPort


@dataclass(frozen=True)
class WorkerContainer:
    core: Container
    dispatcher: PipelineDispatcher
    #: One consumer per stream, so each stream has its own job concurrency.
    consumers: dict[str, RedisStreamConsumer]
    #: Closes worker-only clients, then the shared ones.
    aclose: Callable[[], Awaitable[None]]


def build_worker_container(settings: Settings) -> WorkerContainer:
    core = build_container(settings)
    closers: list[Callable[[], Awaitable[None]]] = []

    downloader = YtDlpAdapter(
        asyncio.Semaphore(settings.download_concurrency),
        core.executor,
        settings.ytdlp_cookies_file,
    )
    # One ffmpeg budget shared by media preparation and rendering.
    ffmpeg_slots = asyncio.Semaphore(settings.ffmpeg_concurrency)
    media = FfmpegMediaAdapter(ffmpeg_slots, core.executor)
    renderer = FfmpegRendererAdapter(
        ffmpeg_slots, core.executor, settings.fonts_dir, settings.characters_dir
    )
    tts = KokoroOnnxAdapter(
        settings.tts_model_path,
        settings.tts_voices_path,
        asyncio.Semaphore(settings.tts_concurrency),
        core.executor,
    )
    lipsync = RhubarbLipSyncAdapter(settings.rhubarb_path, asyncio.Semaphore(2))
    vad = SileroOnnxAdapter(
        settings.vad_model_path, asyncio.Semaphore(settings.vad_concurrency), core.executor
    )
    face_tracker = OnnxFaceTrackerAdapter(
        settings.face_model_path,
        settings.asd_model_path,
        asyncio.Semaphore(settings.track_concurrency),
        core.executor,
        threads=settings.track_threads,
        durations=settings.asd_durations,
    )
    stt = _build_stt(settings, core.executor, closers)
    llm = _build_llm(settings, closers)

    preparation = MediaPreparationService(videos=core.videos, storage=core.storage, media=media)
    exporter = ClipExportService(
        clips=core.clips,
        videos=core.videos,
        jobs=core.jobs,
        storage=core.storage,
        scheduler=core.scheduler,
        renderer=renderer,
        post_platforms=settings.post_platform_list,
    )
    tracking = ClipTrackingService(
        clips=core.clips,
        videos=core.videos,
        jobs=core.jobs,
        storage=core.storage,
        scheduler=core.scheduler,
        tracker=face_tracker,
        min_shot_seconds=settings.track_min_shot_seconds,
        exports=exporter,
    )
    auto_export = settings.auto_export or settings.auto_track
    analysis_stream = JobType.ANALYZE.stream
    dispatcher = PipelineDispatcher(
        jobs=core.jobs,
        videos=core.videos,
        scheduler=core.scheduler,
        progress=core.progress,
        handlers={
            JobType.PING: PingService(),
            JobType.INGEST: IngestService(
                videos=core.videos, storage=core.storage, downloader=downloader
            ),
            JobType.NORMALIZE: preparation.normalize,
            JobType.PREPARE: preparation.prepare,
            JobType.VAD: SpeechDetectionService(videos=core.videos, storage=core.storage, vad=vad),
            JobType.TRANSCRIBE: TranscriptionService(
                videos=core.videos, storage=core.storage, stt=stt, language=settings.stt_language
            ),
            JobType.ANALYZE: AnalysisRouter(
                videos=core.videos,
                clipping=HighlightAnalysisService(
                    videos=core.videos,
                    storage=core.storage,
                    clips=core.clips,
                    llm=llm,
                    min_seconds=settings.clip_min_seconds,
                    max_seconds=settings.clip_max_seconds,
                    max_count=settings.clip_max_count,
                    window_seconds=settings.llm_window_seconds,
                    clips_per_window=settings.llm_clips_per_window,
                    max_overlap=settings.clip_max_overlap,
                    auto_zoom=settings.auto_zoom,
                    tracking=tracking if settings.auto_track else None,
                    exports=exporter if auto_export else None,
                ),
                stories=StoryClipService(
                    videos=core.videos,
                    storage=core.storage,
                    clips=core.clips,
                    llm=llm,
                    part_max_seconds=settings.story_part_max_seconds,
                    exports=exporter if auto_export else None,
                ),
            ),
            JobType.NARRATE: StoryNarrationService(
                videos=core.videos,
                storage=core.storage,
                tts=tts,
                lipsync=lipsync,
                llm=llm,
                pause_seconds=settings.tts_pause_seconds,
            ),
            JobType.COMPOSE: StoryCompositionService(
                videos=core.videos, storage=core.storage, media=media
            ),
            JobType.BACKGROUND: BackgroundLibraryService(
                storage=core.storage,
                jobs=core.jobs,
                scheduler=core.scheduler,
                downloader=downloader,
                media=media,
            ),
            JobType.EXPORT: exporter,
            JobType.TRACK: tracking,
        },
        max_attempts=settings.job_max_attempts,
        # One video at a time through the analysis stages; only safe with one consumer slot.
        inline_streams=frozenset({analysis_stream} if settings.analysis_concurrency == 1 else ()),
        storage=core.storage,
    )
    consumers = {
        stream: RedisStreamConsumer(
            core.redis,
            consumer_name=settings.worker_name,
            concurrency=(
                settings.analysis_concurrency
                if stream == analysis_stream
                else settings.job_concurrency
            ),
        )
        for stream in {job_type.stream for job_type in JobType}
    }

    async def aclose() -> None:
        for close in closers:
            await close()
        await core.aclose()

    return WorkerContainer(core=core, dispatcher=dispatcher, consumers=consumers, aclose=aclose)


def _build_stt(
    settings: Settings, executor: Executor, closers: list[Callable[[], Awaitable[None]]]
) -> STTPort:
    semaphore = asyncio.Semaphore(settings.stt_concurrency)
    if settings.stt_provider == "openai_compat":
        client = AsyncOpenAI(
            base_url=settings.stt_base_url,
            # Local servers ignore the key, but the SDK insists on one.
            api_key=settings.stt_api_key or "unused",
            max_retries=5,
            timeout=300,
        )
        closers.append(client.close)
        return OpenAICompatSTTAdapter(client, settings.stt_model, semaphore, executor)
    return FasterWhisperAdapter(
        settings.stt_model,
        settings.stt_concurrency,
        semaphore,
        executor,
        device=settings.stt_device,
        compute_type=settings.stt_compute_type,
    )


def _build_llm(settings: Settings, closers: list[Callable[[], Awaitable[None]]]) -> LLMPort:
    semaphore = asyncio.Semaphore(settings.llm_concurrency)
    if settings.llm_provider == "anthropic":
        client = AsyncAnthropic(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            max_retries=5,
            timeout=settings.llm_timeout_seconds,
        )
        closers.append(client.close)
        return AnthropicLLMAdapter(client, settings.llm_model, semaphore)
    client = AsyncOpenAI(
        base_url=settings.llm_base_url,
        # Ollama ignores the key, but the SDK insists on one.
        api_key=settings.llm_api_key or "unused",
        max_retries=5,
        timeout=settings.llm_timeout_seconds,
    )
    closers.append(client.close)
    return OpenAICompatLLMAdapter(client, settings.llm_model, semaphore)
