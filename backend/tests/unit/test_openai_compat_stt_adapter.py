import asyncio
import wave
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from openai import AsyncOpenAI

from src.adapters.output.stt.openai_compat_stt_adapter import OpenAICompatSTTAdapter, to_transcript
from src.domain.exceptions import TranscriptionException
from src.domain.models.speech import TimeSpan


def write_wav(path, seconds):
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(b"\x00\x00" * int(16000 * seconds))
    return path


VERBOSE = {
    "language": "english",
    "text": "Good morning. Welcome back.",
    "segments": [
        {"id": 0, "start": 0.0, "end": 1.2, "text": " Good morning."},
        {"id": 1, "start": 1.5, "end": 3.0, "text": " Welcome back."},
    ],
    "words": [
        {"word": "Good", "start": 0.0, "end": 0.5},
        {"word": "morning.", "start": 0.6, "end": 1.2},
        {"word": "Welcome", "start": 1.5, "end": 2.1},
        {"word": "back.", "start": 2.2, "end": 3.0},
    ],
}


def test_words_are_assigned_to_their_segments():
    transcript = to_transcript(VERBOSE)
    assert [[w.text for w in s.words] for s in transcript.segments] == [
        ["Good", "morning."],
        ["Welcome", "back."],
    ]


def test_words_without_segments_become_one_segment():
    transcript = to_transcript({"text": "Good morning.", "words": VERBOSE["words"][:2]})
    [segment] = transcript.segments
    assert (segment.start, segment.end, len(segment.words)) == (0.0, 1.2, 2)


def adapter(handler, executor):
    client = AsyncOpenAI(
        base_url="http://stt.test/v1",
        api_key="k",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return OpenAICompatSTTAdapter(client, "whisper-1", asyncio.Semaphore(2), executor)


async def test_sends_only_the_span_and_asks_for_word_timestamps(tmp_path):
    wav = write_wav(tmp_path / "audio.wav", seconds=10)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read()
        seen["path"] = request.url.path
        seen["body"] = body
        return httpx.Response(200, json=VERBOSE)

    with ThreadPoolExecutor(1) as executor:
        transcript = await adapter(handler, executor).transcribe(
            wav, TimeSpan(start=2, end=4), language="en"
        )

    assert seen["path"] == "/v1/audio/transcriptions"
    body = seen["body"]
    assert b'name="timestamp_granularities[]"\r\n\r\nword' in body
    assert b'name="response_format"\r\n\r\nverbose_json' in body
    assert b'name="language"\r\n\r\nen' in body
    # 2 s of 16 kHz 16-bit mono audio plus a 44-byte header.
    assert len(transcript.segments) == 2
    assert 2 * 16000 * 2 + 44 <= len(body) < 2 * 16000 * 2 + 2000


async def test_api_errors_become_transcription_errors(tmp_path):
    wav = write_wav(tmp_path / "audio.wav", seconds=1)

    def handler(request):
        return httpx.Response(500, json={"error": {"message": "overloaded"}})

    with ThreadPoolExecutor(1) as executor, pytest.raises(TranscriptionException):
        await adapter(handler, executor).transcribe(wav, TimeSpan(start=0, end=1), None)
