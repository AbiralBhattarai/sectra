import io
import wave

import httpx
import pytest

import app as server

MLX_RESULT = {
    "text": " Good morning. Welcome back.",
    "language": "en",
    "segments": [
        {
            "start": 0.0,
            "end": 1.2,
            "text": " Good morning.",
            "words": [
                {"word": " Good", "start": 0.0, "end": 0.5, "probability": 0.9},
                {"word": " morning.", "start": 0.6, "end": 1.2, "probability": 0.9},
            ],
        },
        {
            "start": 1.5,
            "end": 3.0,
            "text": " Welcome back.",
            "words": [
                {"word": " Welcome", "start": 1.5, "end": 2.1, "probability": 0.8},
                {"word": " ", "start": 2.1, "end": 2.1, "probability": 0.1},
                {"word": " back.", "start": 2.2, "end": 3.0, "probability": 0.8},
            ],
        },
    ],
}


def wav_bytes(seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buffer.getvalue()


def test_words_are_flattened_out_of_segments():
    body = server.to_verbose_json(MLX_RESULT)
    assert [w["word"] for w in body["words"]] == ["Good", "morning.", "Welcome", "back."]
    assert [(s["id"], s["start"], s["end"]) for s in body["segments"]] == [
        (0, 0.0, 1.2),
        (1, 1.5, 3.0),
    ]
    assert (body["language"], body["duration"], body["text"]) == (
        "en",
        3.0,
        "Good morning. Welcome back.",
    )


def test_no_speech():
    assert server.to_verbose_json({"text": "", "segments": []})["words"] == []


@pytest.fixture
def calls(monkeypatch):
    seen = []

    def fake(path, model, language):
        with wave.open(path) as w:  # the upload really reached disk as a WAV
            seen.append((model, language, w.getframerate()))
        return MLX_RESULT

    monkeypatch.setattr(server, "transcribe", fake)
    return seen


async def test_endpoint_accepts_sectras_request(calls):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/transcriptions",
            files={"file": ("chunk.wav", wav_bytes(), "audio/wav")},
            data={
                "model": "mlx-community/whisper-small-mlx",
                "language": "en",
                "response_format": "verbose_json",
                "timestamp_granularities[]": ["word", "segment"],
            },
        )
    assert response.status_code == 200
    assert response.json()["words"][0] == {"word": "Good", "start": 0.0, "end": 0.5}
    assert calls == [("mlx-community/whisper-small-mlx", "en", 16000)]


async def test_language_is_optional(calls):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/audio/transcriptions", files={"file": ("chunk.wav", wav_bytes(), "audio/wav")}
        )
    assert response.status_code == 200
    assert calls == [(server.DEFAULT_MODEL, None, 16000)]
