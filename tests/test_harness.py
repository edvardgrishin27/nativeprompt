"""Рекомендация харнесса: форма задачи → команда для нужного CLI."""

from nativeprompt.harness import recommend_harness

CLAUDE = {"family": "claude"}
OPENAI = {"family": "openai"}


def test_goal_claude():
    rec = recommend_harness("Мигрируй модуль, пока все тесты не пройдут", CLAUDE)
    assert rec["shape"] == "goal"
    assert "/goal" in rec["command"]
    assert rec["cli"] == "Claude Code"
    assert rec["source"].startswith("https://code.claude.com")


def test_goal_codex():
    rec = recommend_harness("Реализуй фичу до конца, пока все тесты не пройдут", OPENAI)
    assert rec["shape"] == "goal"
    assert "/goal" in rec["command"]
    assert rec["cli"] == "Codex"


def test_loop_claude():
    rec = recommend_harness("Каждое утро прогоняй триаж по новым issue", CLAUDE)
    assert rec["shape"] == "loop"
    assert "/loop" in rec["command"]


def test_workflow_claude():
    rec = recommend_harness("Проверь все файлы маршрутов на пропущенную авторизацию", CLAUDE)
    assert rec["shape"] == "workflow"
    assert "воркфлоу" in rec["command"] or "ultracode" in rec["command"]


def test_planning():
    rec = recommend_harness("Спроектируй, какой подход выбрать для OAuth", CLAUDE)
    assert rec["shape"] == "planning"
    assert "plan" in rec["command"].lower()


def test_trivial_direct():
    rec = recommend_harness("переименуй x в y", CLAUDE)
    assert rec["shape"] in ("trivial", "normal")
    assert "просто" in rec["command"].lower()
