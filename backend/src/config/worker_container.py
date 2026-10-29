import asyncio
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from dataclasses import dataclass

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from src.adapters.input.worker.redis_stream_consumer import RedisStreamConsumer
from src.adapters.output.downloader.yt_dlp_adapter import YtDlpAdapter
from src.adapters.output.llm.anthropic_adapter import AnthropicLLMAdapter
from src.adapters.output.llm.openai_compat_adapter import OpenAICompatLLMAdapter
from src.adapters.output.media.ffmpeg_media_adapter import FfmpegMediaAdapter
from src.adapters.output.renderer.ffmpeg_renderer_adapter import FfmpegRendererAdapter
from src.adapters.output.stt.faster_whisper_adapter import FasterWhisperAdapter
from src.adapters.output.stt.openai_compat_stt_adapter import OpenAICompatSTTAdapter
from src.adapters.output.vad.silero_onnx_adapter import SileroOnnxAdapter
from src.application.services.clip_export_service import ClipExportService
from src.application.services.highlight_analysis_service import HighlightAnalysisService
from src.application.services.ingest_service import IngestService
from src.application.services.media_preparation_service import MediaPreparationService
from src.application.services.ping_service import PingService
from src.application.services.pipeline_dispatcher import PipelineDispatcher
from src.application.services.speech_detection_service import SpeechDetectionService
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
    renderer = FfmpegRendererAdapter(ffmpeg_slots, core.executor, settings.fonts_dir)
    vad = SileroOnnxAdapter(
        settings.vad_model_path, asyncio.Semaphore(settings.vad_concurrency), core.executor
    )
    stt = _build_stt(settings, core.executor, closers)
    llm = _build_llm(settings, closers)

    preparation = MediaPreparationService(videos=core.videos, storage=core.storage, media=media)
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
            JobType.ANALYZE: HighlightAnalysisService(
                videos=core.videos,
                storage=core.storage,
                clips=core.clips,
                llm=llm,
                min_seconds=settings.clip_min_seconds,
                max_seconds=settings.clip_max_seconds,
                max_count=settings.clip_max_count,
                window_seconds=settings.llm_window_seconds,
            ),
            JobType.EXPORT: ClipExportService(
                clips=core.clips,
                videos=core.videos,
                jobs=core.jobs,
                storage=core.storage,
                scheduler=core.scheduler,
                renderer=renderer,
            ),
        },
        max_attempts=settings.job_max_attempts,
    )
    consumers = {
        stream: RedisStreamConsumer(
            core.redis, consumer_name=settings.worker_name, concurrency=settings.job_concurrency
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
    return FasterWhisperAdapter(settings.stt_model, settings.stt_concurrency, semaphore, executor)


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
