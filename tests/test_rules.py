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
    "gemini": {"gemini-context-file"},
    "grok": {"grok-context-file"},
    "kimi": {"kimi-context-file"},
    "qwen": {"qwen-context-file"},
}

#: `anytime` используют семейства-заглушки, у которых один режим запуска.
VALID_WHEN = {"trivial", "normal", "planning", "goal", "loop", "workflow", "anytime"}
VALID_SHAPES = VALID_WHEN | {"normal"}


ВСЕ_СЕМЕЙСТВА = ["claude", "openai", "gemini", "grok", "kimi", "qwen"]


def test_families_present():
    fams = set(catalog.available_families())
    assert set(ВСЕ_СЕМЕЙСТВА) == fams, "список семейств разошёлся с файлами правил"


@pytest.mark.parametrize("family", ВСЕ_СЕМЕЙСТВА)
def test_rule_ids_frozen(family):
    data = catalog.load_family(family)
    ids = {r["id"] for r in data["rules"]}
    assert ids == FROZEN[family], "Набор правил %s изменился — обнови FROZEN осознанно" % family


@pytest.mark.parametrize("family", ВСЕ_СЕМЕЙСТВА)
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


@pytest.mark.parametrize("family", ВСЕ_СЕМЕЙСТВА)
def test_harness_valid(family):
    data = catalog.load_family(family)
    h = data.get("harness")
    assert h and h.get("commands")
    whens = {c["when"] for c in h["commands"]}
    assert whens <= VALID_WHEN, f"{family}: неизвестная ветка {whens - VALID_WHEN}"
    # Заглушкам хватает одного режима; у полноценных семейств режимы обязаны быть.
    if family in ("claude", "openai"):
        assert {"trivial", "normal", "planning", "goal"} <= whens
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


def test_каждое_удаляющее_правило_имеет_ветку_в_переписчике():
    """Класс «отчёт обещает правку, которой нет».

    `fable5-no-show-thinking` стоял с `action: remove`, ветки под него в rewrite
    не было, и отчёт печатал «[-] Убрать», пока текст оставался прежним. Пин на
    одно правило класс не закрывает — проверяем ВСЕ семейства разом.
    """
    import io
    import os

    корень = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(
        os.path.join(корень, "nativeprompt", "rewrite.py"), encoding="utf-8"
    ).read()
    без_ножа = []
    for family in ВСЕ_СЕМЕЙСТВА:
        for rule in catalog.load_family(family)["rules"]:
            if rule.get("action") == "remove" and '"%s"' % rule["id"] not in src:
                без_ножа.append("%s/%s" % (family, rule["id"]))
    assert not без_ножа, "обещают удаление, но ветки в rewrite нет: %s" % без_ножа


#: Промпты, на которых проверяется, что детектор не обещает больше, чем режет нож.
КОРПУС_ДЛЯ_НОЖЕЙ = [
    "Explain the release process step by step for @docs/release.md",
    "Use chain of thought when fixing @a.py",
    "Реализуй парсер в @a.py, думай пошагово",
    "Опиши пошагово процесс деплоя в @docs/deploy.md",
    "Почини @a.py, покажи ход мыслей и прогони тесты",
    "Распиши рассуждения о рисках миграции и почини @db.py",
    "Report only the most important findings for @a.py",
    "Покажи только самое важное по @a.py",
    "Не мог бы ты починить @a.py",
    "ОБЯЗАТЕЛЬНО почини @a.py",
]


@pytest.mark.parametrize("prompt", КОРПУС_ДЛЯ_НОЖЕЙ)
@pytest.mark.parametrize("model", ["claude-opus-5", "claude-fable-5", "gpt-5.6"])
def test_детектор_не_обещает_больше_чем_режет_нож(prompt, model):
    """Класс «отчёт обещает правку, которой нет» — проверкой, а не комментарием.

    Дважды получалось так: детектор ловил шире, чем умеет нож, и отчёт печатал
    «[-] Убрать», пока текст оставался прежним. Grep по исходнику этого не видит —
    ветка есть, а срабатывания на конкретной фразе нет. Поэтому проверяем на
    корпусе: если правило с `action: remove` сработало, текст обязан измениться.
    """
    from nativeprompt.explain import build_report

    r = build_report(prompt, model)
    удаляющие = [f for f in r["findings"] if f.get("action") == "remove" and not f["always"]]
    if удаляющие and r["original"].strip() == r["improved"].split("\n")[0].strip():
        pytest.fail(
            "правила %s обещали удаление, текст не изменился: %r"
            % ([f["id"] for f in удаляющие], prompt)
        )
