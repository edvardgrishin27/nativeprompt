"""Режимы audit и migrate, улика в находке.

audit проверяет файлы постоянных инструкций и печатает `файл:строка: id`.
Ошибиться здесь можно в две стороны: засыпать человека советами для задачи
(«нет контракта результата» в CLAUDE.md — шум) или промолчать на строке,
ради которой режим и сделан. Обе стороны проверяются.
"""

import json
import os

from nativeprompt import detect
from nativeprompt.__main__ import main
from nativeprompt.analyze import analyze, evidence, mask_code
from nativeprompt.audit import audit_paths, audit_text, collect_files
from nativeprompt.migrate import migrate

FABLE = detect.resolve(explicit="claude-fable-5-2")


def test_улика_указывает_строку():
    текст = "Почини баг.\nОтвечай сразу, без размышлений.\n"
    f = [x for x in analyze(текст, FABLE) if x["check"] == "think_less"][0]
    assert f["evidence"][0]["line"] == 2
    assert "без размышлений" in f["evidence"][0]["text"]


def test_улики_нет_у_детектора_целого_промпта():
    """«Нет контекста» судит о промпте целиком: фрагмента нет."""
    f = [x for x in analyze("почини баг в функции", FABLE) if x["check"] == "missing_context"]
    assert f and f[0]["evidence"] == []


def test_код_не_улика():
    текст = "Объясни код:\n```\n# never retry\n```\n"
    assert evidence("absolute_rule", mask_code(текст), текст) == []


def test_запрет_с_причиной_не_находка():
    assert not audit_text("- Never use raw new — use smart pointers\n", FABLE)
    assert not audit_text("Никогда не пушь в main, потому что там прод.\n", FABLE)
    assert audit_text("- Never retry\n", FABLE)


def test_аудит_не_даёт_советов_задачи():
    находки = audit_text("# Проект\nОтвечай по-русски.\nНикогда не повторяй запросы.\n", FABLE)
    ids = {f["id"] for f in находки}
    assert ids == {"fable52-scope-absolute-rules"}, ids


def test_ignore_в_файле(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("Никогда не повторяй запросы.\n<!-- nativeprompt: ignore fable52-scope-absolute-rules -->\n",
                 encoding="utf-8")
    assert audit_paths([str(p)], target=FABLE)["findings"] == []


def test_сбор_файлов(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    (tmp_path / ".claude" / "agents").mkdir(parents=True)
    (tmp_path / ".claude" / "agents" / "review.md").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "AGENTS.md").write_text("x", encoding="utf-8")
    имена = sorted(os.path.relpath(f, tmp_path) for f in collect_files([str(tmp_path)]))
    assert имена == [os.path.join(".claude", "agents", "review.md"), "CLAUDE.md"]


def test_fail_on_для_ci(tmp_path, capsys):
    p = tmp_path / "AGENTS.md"
    p.write_text("Never retry.\n", encoding="utf-8")
    assert main(["audit", str(p), "--model", "claude-fable-5-2"]) == 0
    assert main(["audit", str(p), "--model", "claude-fable-5-2", "--fail-on", "any"]) == 1
    вывод = capsys.readouterr().out
    assert "%s:1: fable52-scope-absolute-rules" % p in вывод


def test_аудит_json(tmp_path, capsys):
    p = tmp_path / "CLAUDE.md"
    p.write_text("Всегда используй субагентов для поиска.\n", encoding="utf-8")
    main(["audit", str(p), "--model", "claude-fable-5-2", "--json"])
    res = json.loads(capsys.readouterr().out)
    assert [(f["id"], f["line"]) for f in res["findings"]] == [("fable52-delegation-push", 1)]


def test_миграция_показывает_только_разницу():
    res = migrate("claude-fable-5-1", "claude-fable-5-2")
    добавлены = {r["id"] for r in res["added"]}
    убраны = {r["id"] for r in res["removed"]}
    assert any(i.startswith("fable52-") for i in добавлены)
    assert all(i.startswith("fable51-") for i in убраны) and убраны
    assert not (добавлены & set(res["kept"]))
    assert res["effort"]["from_default"] == "high" and res["effort"]["to_default"] == "medium"


def test_миграция_в_том_же_наследовании():
    """Sonnet 5 → 5.5: правила Sonnet 5 остаются (rules_of), уходить нечему."""
    res = migrate("claude-sonnet-5", "claude-sonnet-5-5")
    assert res["removed"] == []
    assert any(r["id"].startswith("sonnet55-") for r in res["added"])
