"""Модели ноября 2026: Claude Fable 5.2, Sonnet 5.5, Haiku 5.5, GPT-6.1 Sol и Terra.

Страницы промптинга этих моделей говорят в основном о строках, которые писали
под прошлые модели и которые теперь мешают. Детекторы под такие строки легко
сделать слишком жадными, поэтому каждый проверяется парой: где обязан сработать
и где обязан промолчать. Отдельно проверяем порядок поколений: «fable-5» —
префикс «fable-5-2», «sonnet-5» — префикс «sonnet-5-5», «gpt-6» — префикс
«gpt-6.1-sol», и при неверном порядке новая модель молча читалась бы как старая.
"""

import json
import os

import pytest

from nativeprompt import detect
from nativeprompt.analyze import _CHECKS
from nativeprompt.effort import recommend_effort
from nativeprompt.explain import build_report

КОРЕНЬ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def чек(имя, текст):
    return bool(_CHECKS[имя](текст, текст.lower(), {}))


def находки(текст, модель):
    return [f["id"] for f in build_report(текст, target=detect.resolve(explicit=модель))["findings"]]


# ── детекторы: сработать и промолчать ────────────────────────────────

ПАРЫ = {
    "think_less": (
        ["отвечай сразу, без размышлений", "ответь не раздумывая", "не думай долго, просто ответь",
         "answer directly without deliberating", "don't overthink it"],
        ["подумай хорошо над архитектурой", "напиши рассуждение о природе времени",
         "почини баг в авторизации", "думай пошагово"],
    ),
    "bare_continue": (
        ["продолжай", "да, продолжай", "го", "ok", "👍", "keep going"],
        ["продолжай чинить авторизацию", "да, запускай миграцию на тестовой базе",
         "дальше перенеси тесты в отдельную папку", ""],
    ),
    "approval_rule": (
        ["спрашивай меня перед любыми действиями", "ничего не отправляй без моего одобрения",
         "ask me before sending messages", "get approval before deploying"],
        ["перед коммитом прогони тесты", "спросил клиент про цену", "почини баг в функции"],
    ),
    "absolute_rule": (
        ["никогда не повторяй запросы", "ни в коем случае не трогай конфиг", "never retry a failed call"],
        ["повторяй запрос до трёх раз", "почини баг в функции авторизации"],
    ),
    "delegate_push": (
        ["всегда используй субагентов для поиска", "делегируй разведку", "spawn subagents for each file"],
        ["агент поддержки отвечает клиентам", "сделай отчёт по агентам продаж"],
    ),
    "token_budget": (
        ["у тебя бюджет 200000 токенов", "осталось 50 000 токенов", "token budget: 100k"],
        ["ответ не длиннее 200 токенов", "посчитай токены в файле"],
    ),
    "treat_done": (
        ["treat that answer as done and focus on the new message", "считай прошлый ответ законченным"],
        ["считай сумму по столбцу", "прошлый ответ был неверным, перепроверь"],
    ),
    "hard_style_limit": (
        ["одна мысль в предложении", "предложения не длиннее 20 слов",
         "one instruction per sentence, in 20 words or fewer"],
        ["напиши текст на 300 слов", "сократи предложения"],
    ),
    "ideas_request": (
        ["предложи идеи для лендинга", "накидай варианты названия", "give me ideas for the dashboard",
         "покажи, что ты умеешь с этим файлом"],
        ["сделай лендинг по макету", "почини баг"],
    ),
    "discourage_tools": (
        ["минимизируй вызовы инструментов", "only use tools when strictly necessary"],
        ["используй инструменты по необходимости", "почини баг"],
    ),
    "hold_findings": (
        ["hold all findings for the final response", "все находки выдай только в финальном ответе"],
        ["в конце напиши итог", "почини баг"],
    ),
    "search_task": (
        ["найди в интернете актуальные цены на подписки", "search the web for the latest version"],
        ["найди баг в функции", "поиск по массиву"],
    ),
    "think_hard": (
        ["think hard about this", "будь тщательным", "подумай как следует над архитектурой"],
        ["ultrathink", "подумай над вариантами A и B", "почини баг"],
    ),
    "undecided": (
        ["хочу rate limiting, но ещё не продумал", "не знаю, как лучше сделать авторизацию"],
        ["добавь лимит 100 запросов в минуту в src/api/limit.ts"],
    ),
    "chatbot_prompt": (
        ["Ты — бот поддержки интернет-магазина", "You are a customer support assistant for Acme"],
        ["напиши функцию для бота в телеграме", "почини баг в авторизации"],
    ),
}


@pytest.mark.parametrize("имя,текст", [(и, т) for и, (да, _) in ПАРЫ.items() for т in да])
def test_детектор_видит(имя, текст):
    assert чек(имя, текст), "%s не увидел: %r" % (имя, текст)


@pytest.mark.parametrize("имя,текст", [(и, т) for и, (_, нет) in ПАРЫ.items() for т in нет])
def test_детектор_молчит(имя, текст):
    assert not чек(имя, текст), "%s сработал зря: %r" % (имя, текст)


def test_отчёт_нужен_только_длинной_работе():
    """«Сделай отчёт о продажах» — содержание задачи, а не итог долгой работы."""
    assert not чек("report_request", "сделай отчёт о продажах в таблице")
    assert чек("report_request", "перенеси модуль, обнови тесты, потом напиши отчёт для команды")


# ── поколения ────────────────────────────────────────────────────────

@pytest.mark.parametrize("ident,gen", [
    ("claude-fable-5-2", "fable-5-2"), ("claude-fable-5.2", "fable-5-2"),
    ("claude-fable-5-1", "fable-5-1"), ("claude-fable-5", "fable-5"),
    ("claude-mythos-5-2", "mythos-5-2"),
    ("claude-sonnet-5-5", "sonnet-5-5"), ("claude-sonnet-5", "sonnet-5"),
    ("claude-haiku-5-5", "haiku-5-5"), ("claude-haiku-4-5", "haiku-4.5"),
    ("gpt-6.1-sol", "gpt-6.1-sol"), ("gpt-6.1-terra", "gpt-6.1-terra"), ("gpt-6-astra", "gpt-6-astra"),
    ("kimi-k3.1-pro", "kimi-k3.1"), ("kimi-k3", "kimi-k3"),
])
def test_новое_поколение_не_читается_как_старое(ident, gen):
    assert detect.resolve(explicit=ident).get("generation") == gen


def test_алиас_fable_ведёт_на_5_2(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_DEFAULT_FABLE_MODEL", raising=False)
    assert detect._build_result("fable", "тест")["generation"] == "fable-5-2"


def test_mythos_5_2_получает_правила_fable_5_2():
    assert any(i.startswith("fable52-") for i in находки("продолжай", "claude-mythos-5-2"))


# ── правила на своих поколениях ──────────────────────────────────────

@pytest.mark.parametrize("префикс,своя,чужая", [
    ("fable52-", "claude-fable-5-2", "claude-fable-5-1"),
    ("sonnet55-", "claude-sonnet-5-5", "claude-sonnet-5"),
    ("haiku55-", "claude-haiku-5-5", "claude-haiku-4-5"),
])
def test_правила_живут_только_на_своём_поколении(префикс, своя, чужая):
    текст = ("перенеси модуль, потом прогони тесты и обнови документацию; "
             "отвечай без размышлений; найди в интернете актуальные цены")
    assert any(i.startswith(префикс) for i in находки(текст, своя)), своя
    assert not any(i.startswith(префикс) for i in находки(текст, чужая)), чужая


def test_sonnet_5_5_наследует_правила_sonnet_5():
    """Вендор: промпты для Sonnet 5 работают и на 5.5 — правила 5 остаются."""
    d = json.load(open(os.path.join(КОРЕНЬ, "nativeprompt", "rules", "claude.json"), encoding="utf-8"))
    assert d["generations"]["sonnet-5-5"]["rules_of"] == "sonnet-5"


def test_источники_ведут_на_свои_страницы():
    d = json.load(open(os.path.join(КОРЕНЬ, "nativeprompt", "rules", "claude.json"), encoding="utf-8"))
    страницы = {"fable52-": "prompting-claude-fable-5-2", "sonnet55-": "prompting-claude-sonnet-5-5",
                "haiku55-": "prompting-claude-haiku-5-5"}
    for r in d["rules"]:
        for префикс, страница in страницы.items():
            if r["id"].startswith(префикс) and r["id"] != "fable52-skip-verification-reminders":
                assert страница in r["source"], r["id"]


# ── уровень усилий ───────────────────────────────────────────────────

@pytest.mark.parametrize("модель", ["claude-fable-5-2", "claude-sonnet-5-5", "claude-haiku-5-5"])
def test_дефолт_medium_в_claude_code(модель):
    rec = recommend_effort(detect.resolve(explicit=модель), "normal")
    assert rec["level"] == "medium" and rec["is_default"]


@pytest.mark.parametrize("модель", ["claude-fable-5-2", "claude-sonnet-5-5", "claude-haiku-5-5"])
def test_долгая_работа_без_человека_на_high(модель):
    """Вендор советует этим моделям high для долгих прогонов: на medium они
    чаще закрывают ход раньше времени. Общий совет «начни с дефолта» спорил бы."""
    rec = recommend_effort(detect.resolve(explicit=модель), "goal")
    assert rec["level"] == "high" and not rec["is_default"]


def test_старые_модели_совет_не_меняют():
    rec = recommend_effort(detect.resolve(explicit="claude-opus-5"), "goal")
    assert rec["level"] == "high" and rec["is_default"]


# ── переписка ────────────────────────────────────────────────────────

def test_владелец_кода_остаётся_за_автором():
    """Инструмент не выбирает за автора, перестраивать код или трогать его
    минимально: в переписке плейсхолдер с обоими вариантами."""
    отчёт = build_report("почини баг в функции авторизации и добавь тест", "claude-fable-5-2")
    assert "fable52-code-ownership" in [f["id"] for f in отчёт["findings"]]
    assert "Код мой, меняй как можно меньше" in отчёт["improved"]


# ── отрицание перед «думай пошагово» ────────────────────────────────

@pytest.mark.parametrize("текст,ждём", [
    ("Не думай пошагово, просто ответь", False),
    ("don't think step by step", False),
    ("Думай пошагово", True),
    ("think step by step", True),
    ("не торопись. Думай пошагово", True),
])
def test_отрицание_не_путается_с_просьбой(текст, ждём):
    """Fable 5.2 при сверке 11.11.2026: «Не думай пошагово» получало совет
    убрать «думай пошагово» — противоположную просьбу."""
    assert чек("forced_cot", текст) is ждём


def test_не_ленись_молчит_там_где_вендор_просит_доделать():
    """Best practices Claude Code: «не ленись» скорее вызовет переработку.
    Но страницы Fable 5.2, Opus 5.5, Sonnet 5.5 и Haiku 5.5 советуют текст
    «доделай до конца» — там совет убрать такую строку спорил бы с вендором."""
    текст = "не ленись, работай пока не закончишь"
    assert "claude-no-keep-going" in находки(текст, "claude-opus-5")
    for модель in ("claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"):
        assert "claude-no-keep-going" not in находки(текст, модель), модель


def test_предел_для_goal_только_при_явном_goal():
    assert "claude-goal-stop-bound" in находки("/goal все тесты auth зелёные", "claude-opus-5")
    assert "claude-goal-stop-bound" not in находки(
        "/goal все тесты auth зелёные или остановись после 20 ходов", "claude-opus-5")
    assert "claude-goal-stop-bound" not in находки(
        "Добавь тест в @src/foo.py; прогони pytest и почини, пока не пройдёт.", "claude-opus-5")


# ── Gemini 3 и Kimi: общие принципы вендоров ────────────────────────

ДАННЫЕ = "\n\n".join(["Строка отчёта номер %d: выручка росла, расходы падали." % i for i in range(60)])


def test_вопрос_в_начале_длинного_контекста():
    assert чек("instruction_first_long", "Сравни два квартала?\n\n" + ДАННЫЕ)
    assert not чек("instruction_first_long", ДАННЫЕ + "\n\nНа основе данных выше сравни два квартала.")
    assert not чек("instruction_first_long", "Сравни два квартала?\n\nкоротко")


def test_разделители_вперемешку():
    assert чек("mixed_delimiters", "# Задача\nсделай\n<context>данные</context>")
    assert not чек("mixed_delimiters", "<task>сделай</task>\n<context>данные</context>")
    assert not чек("mixed_delimiters", "# Задача\nсделай\n## Контекст\nданные")


def test_правила_gemini_и_kimi_ведут_к_вендору():
    for fam, домен in (("gemini", "aistudio.google.com"), ("kimi", "platform.kimi.ai")):
        d = json.load(open(os.path.join(КОРЕНЬ, "nativeprompt", "rules", fam + ".json"), encoding="utf-8"))
        новые = [r for r in d["rules"] if not r["id"].endswith("context-file")]
        assert новые and all(домен in r["source"] for r in новые), fam
