"""Определение модели → семейство + поколение (мягкая деградация)."""

import pytest

from nativeprompt import detect
from nativeprompt.detect import _family_from_id
from nativeprompt.catalog import generation_for


def _isolate_detection_environment(monkeypatch):
    for key in (
        "ANTHROPIC_MODEL",
        "OPENAI_MODEL",
        "CODEX_MODEL",
        "CODEX_THREAD_ID",
        "CODEX_SHELL",
        "CODEX_CI",
        "CLAUDECODE",
        "CLAUDE_CODE_ENTRYPOINT",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(detect, "_read_claude_settings", lambda: None)
    monkeypatch.setattr(detect, "_read_codex_config", lambda: None)


@pytest.mark.parametrize("mid,fam", [
    ("claude-opus-5", "claude"),
    ("claude-sonnet-5", "claude"),
    ("opus", "claude"),
    ("claude-opus-6", "claude"),          # будущая версия → всё равно claude
    ("gpt-5.6", "openai"),
    ("gpt-5", "openai"),
    ("codex", "openai"),
    ("o3", "openai"),
    ("некая-неведомая-модель", None),
])
def test_family_from_id(mid, fam):
    assert _family_from_id(mid) == fam


@pytest.mark.parametrize("mid,gen", [
    ("claude-opus-5", "opus-5"),
    ("claude-sonnet-5", "sonnet-5"),
    ("opus", None),                        # без версии — семейство без поколения
    ("claude-opus-6", None),               # неизвестное поколение
])
def test_generation(mid, gen):
    assert generation_for("claude", mid) == gen


def test_resolve_explicit():
    r = detect.resolve("claude-opus-5")
    assert r["family"] == "claude"
    assert r["generation"] == "opus-5"
    assert r["cli"] == "Claude Code"


def test_resolve_family_alias():
    r = detect.resolve("codex")
    assert r["family"] == "openai"


def test_resolve_unknown():
    r = detect.resolve("совсем-непонятно-что")
    assert r["family"] is None


def test_codex_session_wins_over_conflicting_model_env(monkeypatch):
    _isolate_detection_environment(monkeypatch)
    monkeypatch.setenv("CODEX_THREAD_ID", "test-thread")
    monkeypatch.setenv("CODEX_MODEL", "gpt-5.6")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5")

    r = detect.resolve()

    assert r["family"] == "openai"
    assert r["model_id"] == "gpt-5.6"
    assert r["source"].startswith("env CODEX_MODEL")


def test_codex_session_ignores_stale_anthropic_env_without_model(monkeypatch):
    _isolate_detection_environment(monkeypatch)
    monkeypatch.setenv("CODEX_THREAD_ID", "test-thread")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5")

    r = detect.resolve()

    assert r["family"] == "openai"
    assert r["model_id"] == "codex"
    assert r["source"] == "активная сессия Codex"


def test_claude_session_wins_over_conflicting_model_env(monkeypatch):
    _isolate_detection_environment(monkeypatch)
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("CODEX_MODEL", "gpt-5.6")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-opus-5")

    r = detect.resolve()

    assert r["family"] == "claude"
    assert r["model_id"] == "claude-opus-5"
    assert r["source"].startswith("env ANTHROPIC_MODEL")
