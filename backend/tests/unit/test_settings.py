import pytest
from pydantic import ValidationError

from src.config.settings import Settings


def test_openai_compat_stt_requires_a_base_url():
    with pytest.raises(ValidationError, match="STT_BASE_URL is required"):
        Settings(_env_file=None, stt_provider="openai_compat")


def test_empty_env_values_fall_back_to_defaults(monkeypatch):
    monkeypatch.setenv("STT_LANGUAGE", "")
    assert Settings(_env_file=None).stt_language is None


def test_anthropic_requires_an_api_key():
    with pytest.raises(ValidationError, match="LLM_API_KEY is required"):
        Settings(_env_file=None, llm_provider="anthropic")


def test_clip_length_bounds_must_be_ordered():
    with pytest.raises(ValidationError, match="CLIP_MIN_SECONDS"):
        Settings(_env_file=None, clip_min_seconds=60, clip_max_seconds=30)
