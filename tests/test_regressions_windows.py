"""Регрессии из внешнего отчёта (Windows, Claude Code, opus-5).

Каждый тест здесь — воспроизведённая жалоба живого пользователя. Свои тесты я
писал на однострочных промптах без разметки и без имён собственных, поэтому ни
одна из этих поломок не ловилась: проверялось только то, что нужное удалилось,
и ни разу — что остальное уцелело.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from nativeprompt.analyze import analyze, task_shape
from nativeprompt.harness import recommend_harness
from nativeprompt.rewrite import _dedupe_sentences, _soften_caps, _tidy

CLAUDE = {"family": "claude", "generation": "opus-5"}


def ids(prompt):
    return {f["id"] for f in analyze(prompt, CLAUDE) if not f["always"]}


# ── порча текста ────────────────────────────────────────────────────
def test_имя_собственное_не_разрывается_точкой():
    """«планировщик Windows» → «планировщик. Windows» — из отчёта, дословно.

    Эвристика склеек не может отличить начало предложения от имени собственного.
    """
    assert _tidy("настрой планировщик Windows") == "Настрой планировщик Windows."
    assert _tidy("обзор рынка в России") == "Обзор рынка в России."
    assert _tidy("проверь через Docker и Redis") == "Проверь через Docker и Redis."


def test_разметка_переживает_чистку():
    """Нумерация и переводы строк не должны схлопываться в один абзац."""
    src = "ВАЖНО: рамки.\n\n1. Первый\n2. Второй\n\nПРОВЕРКА: тесты."
    got = _tidy(_soften_caps(src))
    assert "1. Первый" in got and "2. Второй" in got
    assert got.count("\n") >= 3, "переводы строк схлопнулись"
    assert "1. Первый." not in got, "точка приклеена к пункту списка"


def test_заголовок_капсом_понижается_а_не_вырезается():
    """Раньше слово «ВАЖНО» удалялось целиком и абзац оставался без заголовка."""
    got = _soften_caps("ВАЖНО: соблюдай рамки")
    assert "ВАЖНО" not in got
    assert "Важно" in got, "слово пропало вместе со смыслом"


def test_дедуп_не_склеивает_строки():
    assert _dedupe_sentences("Строка один.\nСтрока два.") == "Строка один.\nСтрока два."


# ── логика правил ───────────────────────────────────────────────────
def test_мелкой_правке_не_навязывают_обвязку():
    """shape=trivial, а требования были «заскоупить» и «добавить проверку»."""
    got = ids("Исправь опечатку в заголовке README")
    assert task_shape("Исправь опечатку в заголовке README") == "trivial"
    assert "claude-scope" not in got
    assert "claude-verification" not in got


def test_краткость_не_равна_тривиальности():
    """«Напиши функцию валидации email» короткая, но не пустяковая."""
    assert task_shape("Напиши функцию валидации email.") == "normal"
    assert "claude-scope" in ids("Напиши функцию валидации email.")


def test_разведке_не_требуют_файл_и_прогон_тестов():
    p = "Сделай обзор рынка электросамокатов в России за 2026 год. Нужны три таблицы."
    got = ids(p)
    assert "claude-scope" not in got, "потребовали @-ссылку там, где файлов нет"
    assert "claude-verification" not in got


def test_текстовая_задача_не_считается_кодом():
    """Глагол «напиши» сам по себе кодом не является."""
    got = ids("Напиши разбор конкурента для отдела продаж")
    assert "claude-scope" not in got
    assert "claude-verification" not in got


def test_короткий_корень_не_ловится_внутри_слова():
    """«апи» находилось внутри «н-апи-ши» и делало любой текст задачей по коду."""
    from nativeprompt.analyze import _CODE_NOUN

    assert not _CODE_NOUN.search("напиши разбор")
    assert _CODE_NOUN.search("дёрни апи партнёра")


def test_явный_формат_пунктами_засчитывается():
    p = "Напиши разбор конкурента. Ответ построй так:\n1) кто они\n2) сильные стороны"
    assert "claude-output-contract" not in ids(p)


def test_проверка_с_требованием_к_результату_не_срезается():
    """«проверь себя: назови источник» — это заказ, а не вежливость."""
    p = ("Сделай обзор рынка. Проверь себя: по каждой цифре назови источник "
         "и скажи, каким цифрам не доверяешь.")
    assert "opus5-remove-verification" not in ids(p)


def test_проверка_с_последствием_не_срезается():
    p = ("Проверь методику. Прогони трудный случай и убедись, что признак всплывает. "
         "Если не всплывёт — признай метод дырявым.")
    assert "opus5-remove-verification" not in ids(p)


def test_голая_просьба_перепроверить_срабатывает():
    """Настоящее срабатывание правила гасить нельзя."""
    assert "opus5-remove-verification" in ids("Почини @a.py, прогони тесты и перепроверь себя.")


# ── совет по режиму запуска ─────────────────────────────────────────
def test_форма_normal_не_выдаётся_за_мелкую_правку():
    """Корзина `normal` вела на ветку `trivial` — совет был уверенным и неверным."""
    research = "Сделай обзор рынка за 2026 год с тремя таблицами и списком источников."
    rec = recommend_harness(research, CLAUDE)
    assert rec["shape"] == "normal"
    assert "без plan/goal" not in rec["title"]

    trivial = recommend_harness("Исправь опечатку в README", CLAUDE)
    assert trivial["shape"] == "trivial"
    assert trivial["title"] != rec["title"], "совет одинаковый для разных форм"


# ── кодировка вывода ────────────────────────────────────────────────
def test_json_остаётся_utf8_при_системной_cp1251():
    """JSON по спецификации обязан быть UTF-8; на Windows вывод падал целиком."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1251"}
    r = subprocess.run(
        [sys.executable, "-m", "nativeprompt", "improve",
         "тест в России", "--model", "claude-opus-5", "--json"],
        capture_output=True, env=env,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")[-400:]
    data = json.loads(r.stdout.decode("utf-8"))
    assert data["target"]["family"] == "claude"
    assert "России" in data["original"], "кириллица доехала целой"
