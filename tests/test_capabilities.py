"""Свойства инструмента. Здесь проверяется НЕ отсутствие багов, а наличие пользы.

Зачем отдельный файл. Четыре круга ревью подряд находили дефекты, и каждый раз
самый безопасный способ их закрыть — снять операцию целиком. Так уже сделано с
вырезанием «перепроверь себя»: три версии подряд оно удаляло не то, и правило
переведено в предупреждение. Решение верное, но повторённое пять раз оно оставит
инструмент, который ничего не делает и потому безупречен.

Поэтому здесь зафиксировано то, ради чего инструмент существует. Если очередная
правка ради чистого отчёта выхолостит его, покраснеет этот файл — сразу, а не
через два круга, когда уже забыто, что там было.
"""

from __future__ import annotations

import pytest

from nativeprompt.explain import build_report

CLAUDE = "claude-opus-5"
CODEX = "gpt-5.6"


def _ids(report):
    return {f["id"] for f in report["findings"]}


# ── 1. Инструмент понимает, для какой модели пишут ──────────────────
def test_определяет_семейство_и_поколение():
    r = build_report("почини баг в @a.py", CLAUDE)
    assert r["target"]["family"] == "claude"
    assert r["target"]["generation"] == "opus-5"


@pytest.mark.parametrize(
    "family,model",
    [("claude", CLAUDE), ("openai", CODEX), ("gemini", "gemini-3-pro"),
     ("qwen", "qwen3-coder"), ("kimi", "kimi-k2"), ("grok", "grok-code")],
)
def test_работает_для_всех_шести_семейств(family, model):
    r = build_report("Напиши функцию валидации email", model)
    assert r["target"]["family"] == family
    assert r["improved"] and r["metaprompt"]


# ── 2. Инструмент находит настоящие пробелы в промпте ───────────────
def test_требует_контекст_и_проверку_у_кодовой_задачи():
    r = build_report("Напиши функцию валидации email", CLAUDE)
    assert {"claude-scope", "claude-verification"} <= _ids(r)


def test_требует_формат_у_текстовой_задачи():
    assert "claude-output-contract" in _ids(build_report("Напиши разбор конкурента", CLAUDE))


def test_дописывает_плейсхолдеры_но_не_придумывает_содержание():
    r = build_report("Напиши функцию валидации email", CLAUDE)
    assert "‹" in r["improved"], "секции-плейсхолдеры пропали"
    # Задачу за автора не додумываем: в плейсхолдере просьба уточнить, а не текст.
    assert "email" not in r["improved"].split("Контекст:")[-1].split("\n")[0]


# ── 3. Правки разные у разных вендоров — это и есть суть ────────────
def test_цепочка_рассуждений_режется_у_codex_и_остаётся_у_claude():
    """Контраст теперь по НАХОДКАМ, а не по тексту.

    `codex-no-forced-cot` больше не вырезает «думай пошагово» — отличить
    навязанную цепочку рассуждений от заказанного формата ответа по форме
    нельзя, поэтому правило только предупреждает (см. rules/openai.json).
    Контраст между вендорами остаётся реальным: у Codex правило срабатывает,
    у Claude такого правила нет вовсе — но текст в обоих случаях цел.
    """
    codex = build_report("Реализуй парсер, думай пошагово", CODEX)
    claude = build_report("Реализуй парсер в @a.py, думай пошагово, прогони тесты", CLAUDE)
    assert "codex-no-forced-cot" in _ids(codex)
    assert not any("cot" in fid for fid in _ids(claude))
    assert "пошагово" in codex["improved"]
    assert "пошагово" in claude["improved"]


def test_правила_поколения_не_применяются_к_чужому():
    """`opus5-*` — только для Opus 5, `fable5-*` — только для Fable 5."""
    opus = _ids(build_report("Почини @a.py и перепроверь себя", CLAUDE))
    fable = _ids(build_report("Почини @a.py и перепроверь себя", "claude-fable-5"))
    assert "opus5-remove-verification" in opus
    assert "opus5-remove-verification" not in fable


# ── 4. Инструмент правит текст там, где это безопасно ───────────────
def test_снимает_капс_давление():
    r = build_report("ОБЯЗАТЕЛЬНО почини @a.py и прогони тесты", CLAUDE)
    assert "ОБЯЗАТЕЛЬНО" not in r["improved"]
    assert "бязательно" in r["improved"], "слово должно остаться, просто без крика"


def test_снимает_вежливую_обёртку():
    r = build_report("Не мог бы ты починить @a.py и прогнать тесты", CLAUDE)
    assert "не мог бы" not in r["improved"].lower()


def test_спорное_помечает_а_не_режет():
    """Граница между «правим» и «показываем» — тоже свойство, а не отсутствие фичи."""
    r = build_report("Почини @a.py и перепроверь себя", CLAUDE)
    assert "opus5-remove-verification" in _ids(r)
    assert "перепроверь себя" in r["improved"]


@pytest.mark.parametrize(
    "rule_id,model,prompt,kept",
    [
        ("codex-no-forced-cot", CODEX, "Реализуй парсер, думай пошагово", "думай пошагово"),
        ("codex-lean", CODEX, "Сделай бэкап базы. Сделай бэкап базы.", "Сделай бэкап базы"),
        ("opus5-report-all", CLAUDE, "Покажи только самое важное.", "только самое важное"),
        ("fable5-no-show-thinking", "claude-fable-5", "Покажи ход мыслей", "ход мыслей"),
    ],
)
def test_переведённые_в_warn_правила_срабатывают_но_не_режут(rule_id, model, prompt, kept):
    """Все четыре правила, переведённые из «режем» в «предупреждаем» шагом 1,
    обязаны вести себя как `opus5-remove-verification` выше: находка есть,
    текст цел. Одно свойство вместо четырёх копий одного и того же теста —
    и оно же ловит будущий рецидив (кто-то случайно вернёт ветку в rewrite).
    """
    r = build_report(prompt, model)
    assert rule_id in _ids(r), r["findings"]
    assert kept in r["improved"], r["improved"]


# ── 5. Совет по режиму запуска ──────────────────────────────────────
def test_советует_режим_под_форму_задачи():
    plan = build_report("Спроектируй архитектуру очереди задач", CLAUDE)
    assert plan["shape"] == "planning"
    assert "plan" in plan["harness"]["command"].lower()

    trivial = build_report("Исправь опечатку в README", CLAUDE)
    assert trivial["shape"] == "trivial"
    assert "просто напиши" in trivial["harness"]["command"].lower()


def test_советы_вне_формы_задачи_доходят_до_пользователя():
    r = build_report("Напиши парсер логов", "grok-code")
    assert r["harness"]["anytime"], "советы /rewind, /effort снова потерялись"


# ── 6. Проверяемость: у всего есть источник ─────────────────────────
def test_у_каждого_правила_есть_ссылка_на_вендора():
    r = build_report("Напиши функцию валидации email", CLAUDE)
    assert r["findings"], "правил не осталось вовсе"
    for f in r["findings"]:
        assert f["source"].startswith("https://"), f["id"]


def test_мета_промпт_собирается_и_несёт_правила():
    r = build_report("Почини баг", CLAUDE)
    mp = r["metaprompt"]
    assert len(mp) > 200
    assert "https://" in mp, "мета-промпт без источников — просто болтовня"
    assert "PROMPT" in mp
