"""Целостность шпаргалок правил + frozen-snapshot набора правил."""

import re

import pytest

from nativeprompt import catalog
from nativeprompt.analyze import _CHECKS

FROZEN = {
    "claude": {
        "claude-scope", "claude-verification", "claude-reference-files",
        "claude-root-cause", "claude-output-contract", "claude-explicit-action",
        "claude-xml", "claude-dial-caps", "opus5-remove-verification",
        "opus5-concise", "opus5-report-all",
        "fable5-no-show-thinking", "fable5-ground-progress", "opus48-encourage-subagents",
    },
    "openai": {
        "codex-no-forced-cot", "codex-outcome-contract", "codex-lean",
        "codex-no-contradiction", "codex-explicit-action", "codex-dial-scaffold",
        "codex-agents-md", "codex-autonomy",
    },
}

VALID_WHEN = {"trivial", "normal", "planning", "goal", "loop", "workflow"}
VALID_SHAPES = VALID_WHEN | {"normal"}


def test_families_present():
    fams = set(catalog.available_families())
    assert {"claude", "openai"} <= fams


@pytest.mark.parametrize("family", ["claude", "openai"])
def test_rule_ids_frozen(family):
    data = catalog.load_family(family)
    ids = {r["id"] for r in data["rules"]}
    assert ids == FROZEN[family], "Набор правил %s изменился — обнови FROZEN осознанно" % family


@pytest.mark.parametrize("family", ["claude", "openai"])
def test_rule_shape(family):
    data = catalog.load_family(family)
    assert data.get("rules_version")
    for r in data["rules"]:
        for key in ("id", "title", "why", "source", "check", "action"):
            assert r.get(key), "%s: правило %s без поля %s" % (family, r.get("id"), key)
        assert r["source"].startswith("https://"), "%s: источник не https" % r["id"]
        assert r["check"] in _CHECKS, "%s: неизвестный check %r" % (r["id"], r["check"])
        assert r["action"] in {"add", "remove", "restructure", "warn"}
        if r.get("when_shapes"):
            assert set(r["when_shapes"]) <= VALID_SHAPES


@pytest.mark.parametrize("family", ["claude", "openai"])
def test_harness_valid(family):
    data = catalog.load_family(family)
    h = data.get("harness")
    assert h and h.get("commands")
    whens = {c["when"] for c in h["commands"]}
    assert whens <= VALID_WHEN
    assert {"trivial", "planning", "goal"} <= whens
    for c in h["commands"]:
        assert c["source"].startswith("https://")
        for key in ("command", "title", "why"):
            assert c.get(key)


def test_sources_manifest():
    src = catalog.load_sources()
    fams = src["families"]
    assert {"claude", "openai"} <= set(fams)
    for fam, info in fams.items():
        assert info["docs"], "нет docs для %s" % fam
        for u in info["docs"]:
            assert u.startswith("https://") and u.endswith(".md"), u


def test_codex_config_notes_separate_cli_and_api_layers():
    """Оба слоя документированы, но их НЕЛЬЗЯ путать:
    CLI-конфиг Codex (~/.codex/config.toml) — model_reasoning_effort / model_verbosity;
    Responses API — reasoning.effort / reasoning.mode / text.verbosity.
    Проверяем, что заметка называет оба и явно их разделяет."""
    data = catalog.load_family("openai")
    notes = " ".join(data.get("config_notes", []))
    # слой CLI
    assert "model_reasoning_effort" in notes
    assert "model_verbosity" in notes
    # слой API (Codex ошибочно удалил их как «недокументированные» — вернули)
    assert "reasoning.mode" in notes
    assert "text.verbosity" in notes
    # слои явно разведены
    assert "config.toml" in notes and "API" in notes
    # у заметок есть источники
    srcs = data.get("config_notes_sources", [])
    assert srcs and all(u.startswith("https://") for u in srcs)
