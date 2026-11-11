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


# ── находки ревью Fable 5.2 (11.11.2026) ────────────────────────────

def test_номер_строки_с_пустыми_строками_в_начале(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("\n\n\n# Rules\nNever retry.\n", encoding="utf-8")
    assert [f["line"] for f in audit_paths([str(p)], target=FABLE)["findings"]] == [5]


def test_bom_не_попадает_в_вывод(tmp_path):
    p = tmp_path / "AGENTS.md"
    p.write_bytes("Never retry.\n".encode("utf-8-sig"))
    assert audit_paths([str(p)], target=FABLE)["findings"][0]["text"] == "Never retry."


def test_несуществующий_путь_это_ошибка(tmp_path):
    assert main(["audit", str(tmp_path / "нет"), "--model", "claude-fable-5-2"]) == 1


def test_непрочитанный_файл_роняет_ci(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_bytes(b"\xff\xfe\x00broken")
    assert main(["audit", str(p), "--model", "claude-fable-5-2", "--fail-on", "any"]) == 1


def test_симлинк_на_каталог_и_цикл(tmp_path):
    настоящий = tmp_path / "real" / "x"
    настоящий.mkdir(parents=True)
    (настоящий / "SKILL.md").write_text("x", encoding="utf-8")
    (tmp_path / "skills").symlink_to(tmp_path / "real")
    (tmp_path / "real" / "loop").symlink_to(tmp_path / "real")
    файлы = collect_files([str(tmp_path / "skills")])
    assert len(файлы) == 1 and файлы[0].endswith("SKILL.md")


def test_ignore_не_захватывает_следующую_строку(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("nativeprompt: ignore fable52-delegation-push\n"
                 "fable52-scope-absolute-rules lives here\nNever retry.\n", encoding="utf-8")
    assert [f["id"] for f in audit_paths([str(p)], target=FABLE)["findings"]] == ["fable52-scope-absolute-rules"]


def test_все_места_а_не_пять(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("".join("Never retry %d.\n" % i for i in range(8)), encoding="utf-8")
    assert len(audit_paths([str(p)], target=FABLE)["findings"]) == 8


def test_корень_обхода_не_влияет_на_набор(tmp_path):
    (tmp_path / "skills" / "x").mkdir(parents=True)
    (tmp_path / "skills" / "x" / "notes.md").write_text("x", encoding="utf-8")
    assert collect_files([str(tmp_path / "skills" / "x")]) == []
    assert len(collect_files([str(tmp_path)])) == 1


def test_миграция_между_вендорами_без_ложного_уровня():
    from nativeprompt.migrate import render_migrate
    assert "УРОВЕНЬ УСИЛИЙ" not in render_migrate(migrate("claude-fable-5-2", "gpt-6.1-sol"))
    assert "не определилась" in render_migrate(migrate("opus", "claude-fable-5-2"))


def test_большой_файл_с_тегами_быстро():
    import time
    from nativeprompt.analyze import _CHECKS
    текст = "# h\n" + "<item> text\n" * 40000
    t0 = time.time()
    assert not _CHECKS["mixed_delimiters"](текст, текст.lower(), {})
    assert time.time() - t0 < 2


def test_корень_с_именем_каталога_инструкций(tmp_path):
    """`audit ~/.claude/rules`: сам корень называется rules — его файлы в счёт."""
    (tmp_path / "rules" / "common").mkdir(parents=True)
    (tmp_path / "rules" / "common" / "style.md").write_text("x", encoding="utf-8")
    assert len(collect_files([str(tmp_path / "rules")])) == 1
