# -*- coding: utf-8 -*-
"""Рекомендация уровня усилий: форма задачи и модель → effort, со ссылкой на вендора.

Данные — блок "effort" в rules/claude.json и rules/openai.json. Здесь проверяется
совет под каждую форму задачи, дефолт каждой модели, подмена уровня, которого
модель не умеет (так же, как это делает сам Claude Code), модели без effort,
вывод в отчёте и то, что уровень не утекает в текст промпта: это настройка
запуска, а не слова, и вендоры просят не подменять её фразами.
"""

import pytest

from nativeprompt import catalog
from nativeprompt.__main__ import main
from nativeprompt.detect import resolve
from nativeprompt.effort import _LADDER, fit_level, recommend_effort
from nativeprompt.explain import build_report, render_report

СЕМЕЙСТВА_С_EFFORT = ["claude", "openai"]
ФОРМЫ = ["trivial", "normal", "planning", "goal", "loop", "workflow"]
#: Совет обязан вести в документацию вендора, как и правила: блог сюда не
#: годится, даже блог самого вендора. Документацию `update` сверяет со снимком,
#: а блог в манифест не попадает, и его правку никто не заметит.
ДОМЕНЫ = {
    "claude": ("https://code.claude.com/", "https://platform.claude.com/"),
    "openai": ("https://developers.openai.com/", "https://learn.chatgpt.com/"),
}


def совет(модель, форма):
    return recommend_effort(resolve(модель), форма)


def _ссылки(eff):
    yield eff["set"]["source"]
    yield eff["levels_source"]
    yield eff["unsupported"]["source"]
    for совет in eff.get("raise_when") or []:
        yield совет["source"]
    for s in eff["by_shape"].values():
        yield s["source"]
        if s.get("caution"):
            yield s["caution"]["source"]
    for m in eff["models"].values():
        if m.get("note"):
            yield m["note_source"]


# ── данные ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("family", СЕМЕЙСТВА_С_EFFORT)
def test_у_каждого_поколения_есть_строка_уровней(family):
    """Модель, добавленная в generations без строки в effort, получила бы совет
    по чужому дефолту. Строка обязательна: уровни и дефолт или явное «effort нет»."""
    data = catalog.load_family(family)
    assert set(data["generations"]) == set(data["effort"]["models"]), (
        "поколения и строки уровней разошлись: %s"
        % (set(data["generations"]) ^ set(data["effort"]["models"])))


@pytest.mark.parametrize("family", СЕМЕЙСТВА_С_EFFORT)
def test_дефолт_модели_входит_в_её_уровни(family):
    for gid, m in catalog.load_family(family)["effort"]["models"].items():
        if m["levels"] is None:
            # Список уровней вендор не публикует; дефолт при этом бывает известен.
            assert m["default"] is None or m["default"] in _LADDER, gid
            continue
        assert all(l in _LADDER for l in m["levels"]), "%s: уровень вне лестницы" % gid
        if m["levels"]:
            assert m["default"] in m["levels"], "%s: дефолт %r не из её уровней" % (gid, m["default"])
        else:
            assert m["default"] is None, "%s: у модели без effort не бывает дефолта" % gid


@pytest.mark.parametrize("family", СЕМЕЙСТВА_С_EFFORT)
def test_совет_есть_под_каждую_форму_задачи(family):
    by_shape = catalog.load_family(family)["effort"]["by_shape"]
    assert set(ФОРМЫ) <= set(by_shape), "нет совета для форм %s" % (set(ФОРМЫ) - set(by_shape))
    for форма, s in by_shape.items():
        assert s["level"] == "default" or s["level"] in _LADDER, "%s: %r" % (форма, s["level"])
        assert len(s["why"]) > 40, "%s: объяснение пустое или отписка" % форма


@pytest.mark.parametrize("family", СЕМЕЙСТВА_С_EFFORT)
def test_каждая_ссылка_ведёт_к_вендору(family):
    eff = catalog.load_family(family)["effort"]
    for url in _ссылки(eff):
        assert url.startswith(ДОМЕНЫ[family]), "%s: ссылка не на вендора: %s" % (family, url)


@pytest.mark.parametrize("family", СЕМЕЙСТВА_С_EFFORT)
@pytest.mark.parametrize("форма", ФОРМЫ)
def test_совет_по_каждой_модели_и_форме_полный(family, форма):
    """Свойство на всей сетке «модель × форма»: у совета есть объяснение и ссылка,
    уровень — из уровней модели, команда подставлена без пустых скобок."""
    data = catalog.load_family(family)
    for gid, m in data["effort"]["models"].items():
        rec = recommend_effort({"family": family, "generation": gid}, форма)
        assert rec["why"] and rec["source"].startswith("https://")
        if m["levels"] == []:
            assert rec["supported"] is False and rec["level"] is None and rec["command"] == ""
            continue
        assert rec["command"] and "{" not in rec["command"], rec["command"]
        if m["levels"] is None:
            # Уровней не знаем: совет либо дефолт, либо уровень с прямой оговоркой.
            assert rec["level"] is None or rec["level"] in _LADDER
            assert rec["is_default"] or rec.get("levels_unknown") or rec.get("unknown_default"), (gid, форма)
            continue
        assert rec["level"] in m["levels"], "%s/%s: %r не из %s" % (gid, форма, rec["level"], m["levels"])


# ── подмена уровня, которого модель не умеет ───────────────────────────
@pytest.mark.parametrize("wanted, levels, expected", [
    ("xhigh", ["low", "medium", "high", "max"], "high"),   # пример из доков Claude Code
    ("max", ["low", "medium", "high", "max"], "max"),
    ("low", ["low", "medium", "high"], "low"),
    ("none", ["low", "medium", "high"], "low"),             # ниже всех — нижняя ступень модели
    ("low", [], None),                                      # effort у модели нет
])
def test_подмена_как_у_claude_code(wanted, levels, expected):
    assert fit_level(wanted, levels) == expected


# ── Claude Code ────────────────────────────────────────────────────────
def test_opus_55_дефолт_medium():
    rec = совет("claude-opus-5-5", "normal")
    assert rec["level"] == "medium" and rec["is_default"]
    assert rec["command"] == "/effort medium"
    assert "medium" in rec["model_note"]["text"], "пропал совет не переносить уровень с Opus 5"


def test_opus_47_дефолт_xhigh():
    rec = совет("claude-opus-4-7", "normal")
    assert rec["level"] == "xhigh" and rec["is_default"]


@pytest.mark.parametrize("модель", ["claude-opus-5", "claude-sonnet-5", "claude-fable-5-1",
                                    "claude-opus-4-8", "claude-opus-4-6", "claude-sonnet-4-6"])
def test_у_остальных_моделей_дефолт_high(модель):
    rec = совет(модель, "normal")
    assert rec["level"] == "high" and rec["is_default"], (модель, rec["level"])


@pytest.mark.parametrize("форма", ["normal", "planning", "goal", "loop"])
def test_у_claude_почти_все_формы_ведут_к_дефолту(форма):
    """Вендор пишет, что дефолт подходит для большинства задач по коду.
    Инструмент не поднимает уровень заранее ни под план, ни под долгую цель."""
    rec = совет("claude-opus-5-5", форма)
    assert rec["level"] == "medium" and rec["is_default"]


def test_механическая_правка_low():
    rec = совет("claude-opus-5-5", "trivial")
    assert rec["level"] == "low" and not rec["is_default"]
    assert rec["command"] == "/effort low"


def test_аудит_по_проекту_ultracode_с_предупреждением_о_лимите():
    rec = совет("claude-opus-5-5", "workflow")
    assert rec["level"] == "ultracode"
    assert "ultracode:" in rec["command"] and "/effort ultracode" in rec["command"]
    assert rec["caution"] and "лимит" in rec["caution"]["text"], "пропало предупреждение о лимите"


def test_без_xhigh_ultracode_подменяется_на_high():
    """Ultracode требует xhigh. Без него Claude Code берёт уровень не выше xhigh,
    а не max, хотя max на лестнице выше: у составного уровня своя граница."""
    rec = совет("claude-opus-4-6", "workflow")
    assert rec["level"] == "high", rec["level"]
    assert "недоступен" in rec["why"]
    assert rec["command"] == "/effort high"


@pytest.mark.parametrize("модель", ["claude-haiku-4-5", "claude-mythos-5-1", "claude-opus-4-5"])
def test_модель_без_effort_не_получает_уровень(модель):
    rec = совет(модель, "planning")
    assert rec["supported"] is False and rec["level"] is None
    assert "нет" in rec["why"]


def test_алиас_без_версии_не_угадывает_дефолт():
    rec = совет("opus", "normal")
    assert rec["level"] is None and "‹уровень›" in rec["command"]
    assert "Opus 5.5" in rec["unknown_default"] and "medium" in rec["unknown_default"]
    # Конкретный совет от модели не зависит и остаётся конкретным.
    assert совет("opus", "trivial")["level"] == "low"


# ── отчёт ──────────────────────────────────────────────────────────────
def test_уровень_есть_в_отчёте():
    r = build_report("Исправь опечатку в README", "claude-opus-5-5")
    assert r["effort"]["level"] == "low"


def test_уровень_печатается_после_совета_по_запуску():
    текст = render_report(build_report("Спроектируй архитектуру очереди задач", "claude-opus-5-5"))
    assert "УРОВЕНЬ УСИЛИЙ (Claude Code · Claude Opus 5.5): medium, это дефолт модели" in текст
    assert текст.index("КАК ЗАПУСКАТЬ") < текст.index("УРОВЕНЬ УСИЛИЙ")
    assert "/effort medium" in текст


def test_модель_без_effort_так_и_названа_в_отчёте():
    текст = render_report(build_report("Спроектируй архитектуру очереди задач", "claude-haiku-4-5"))
    assert "у этой модели effort нет" in текст


@pytest.mark.parametrize("модель", ["claude-opus-5-5", "gpt-6-astra"])
def test_уровень_не_утекает_в_текст_промпта(модель):
    """Уровень ставят настройкой. В улучшенный промпт и в мета-промпт он не идёт."""
    r = build_report("Проверь все файлы маршрутов на пропущенную авторизацию", модель)
    for поле in ("improved", "metaprompt"):
        assert "/effort" not in r[поле] and "reasoning_effort" not in r[поле], поле


@pytest.mark.parametrize("модель", ["gemini-2.5-pro", "grok-4", "kimi", "qwen"])
def test_семейства_без_данных_молчат(модель):
    """Нет данных вендора — нет совета. Выдумывать уровень инструмент не станет."""
    r = build_report("Спроектируй архитектуру очереди задач", модель)
    assert r["effort"] is None
    assert "УРОВЕНЬ УСИЛИЙ" not in render_report(r)


def test_rules_печатает_таблицу_уровней(capsys):
    assert main(["rules", "claude"]) == 0
    вывод = capsys.readouterr().out
    assert "УРОВЕНЬ УСИЛИЙ (Claude Code)" in вывод
    assert "Claude Opus 5.5        low · medium* · high · xhigh · max · ultracode" in вывод
    assert "Claude Haiku 4.5       effort нет" in вывод


# ── Codex ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("модель, старт", [
    ("gpt-6-sol", "medium"), ("gpt-6-luna", "high"), ("gpt-6-astra", "low"),
])
def test_codex_стартовый_уровень_по_модели(модель, старт):
    """learn.chatgpt.com: «Start with Medium for Sol, High for Luna, or Light for
    Astra. In configuration, Astra's Light setting is low»."""
    rec = совет(модель, "normal")
    assert rec["level"] == старт and rec["is_default"]
    assert rec["default_label"] == "с него вендор советует начинать"
    assert rec["command"].startswith('model_reasoning_effort = "%s"' % старт)


def test_codex_мелкая_правка_low():
    assert совет("gpt-6-sol", "trivial")["level"] == "low"


@pytest.mark.parametrize("модель, уровень", [
    ("gpt-6-astra", "medium"),   # Astra начинает с low — под план поднимаем
    ("gpt-6-sol", "medium"),
    ("gpt-6-luna", "high"),      # Luna начинает с high — ниже не опускаем
])
def test_codex_план_не_ниже_стартового_уровня(модель, уровень):
    rec = совет(модель, "planning")
    assert rec["level"] == уровень, (модель, rec["level"])
    assert "plan_mode_reasoning_effort" in rec["caution"]["text"], "пропала оговорка про свой уровень у /plan"


@pytest.mark.parametrize("модель", ["gpt-6-astra", "gpt-6-sol", "gpt-6-luna"])
def test_codex_долгая_цель_high(модель):
    assert совет(модель, "goal")["level"] == "high"


def test_codex_аудит_по_проекту_ultra():
    rec = совет("gpt-6-sol", "workflow")
    assert rec["level"] == "ultra"
    assert "Ultra in model picker slider" in rec["caution"]["text"]


def test_у_luna_нет_ultra_и_совет_честно_подменяется():
    """«GPT-6 Luna supports reasoning efforts up to Max, but not Ultra». Подмена —
    на xhigh по гайду OpenAI (ревью кода и аудит), а не на max: max — это время
    на одну задачу, а не деление работы на части."""
    rec = совет("gpt-6-luna", "workflow")
    assert rec["level"] == "xhigh"
    assert "Ultra нет" in rec["why"]
    assert rec["source"].startswith("https://developers.openai.com/api/docs/guides/reasoning")
    assert rec["caution"] is None, "оговорка про включение Ultra не относится к Luna"


def test_неизвестный_список_уровней_назван_прямо():
    rec = совет("codex", "workflow")
    assert rec["level"] == "ultra"
    assert "ultra" in rec["levels_unknown"] and "/model" in rec["levels_unknown"]
    # У GPT-5.6 список уровней не опубликован, но дефолт известен из гайда OpenAI.
    rec = совет("gpt-5.6", "normal")
    assert rec["level"] == "medium" and rec["is_default"]


def test_codex_заметка_про_уровни_в_конфиге_не_устарела():
    """В 0.8.1 заметка называла уровни CLI «minimal|low|medium|high|xhigh», а
    справочник конфига Codex уже перечислял low…max и ultra."""
    notes = " ".join(catalog.load_family("openai")["config_notes"])
    assert "minimal|" not in notes
    assert "ultra" in notes and "plan_mode_reasoning_effort" in notes


def test_codex_уровень_печатается_в_отчёте():
    текст = render_report(build_report("Спроектируй архитектуру очереди задач", "gpt-6-luna"))
    assert "УРОВЕНЬ УСИЛИЙ (Codex · GPT-6 Luna): high, с него вендор советует начинать" in текст


def test_json_несёт_уровень(capsys):
    """Навык Claude Code ходит через --json: без ключа `effort` он не узнал бы о совете."""
    import json as _json
    assert main(["improve", "Спроектируй архитектуру очереди задач", "--model", "gpt-6-sol", "--json"]) == 0
    отчёт = _json.loads(capsys.readouterr().out)
    assert отчёт["effort"]["level"] == "medium"
    assert отчёт["effort"]["source"].startswith("https://learn.chatgpt.com/")


def test_rules_печатает_стартовые_уровни_codex(capsys):
    assert main(["rules", "codex"]) == 0
    вывод = capsys.readouterr().out
    assert "Уровни по моделям (* — стартовый уровень вендора)" in вывод
    assert "GPT-6 Luna" in вывод and "high*" in вывод
    assert "список уровней вендор не публикует; стартовый: medium" in вывод
