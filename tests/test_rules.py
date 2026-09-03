"""Целостность шпаргалок правил + frozen-snapshot набора правил."""

import re

import pytest

from nativeprompt import catalog
from nativeprompt.analyze import _CHECKS
from nativeprompt.update import _all_urls

FROZEN = {
    "claude": {
        "claude-dial-caps",
        "claude-explicit-action",
        "claude-output-contract",
        "claude-reference-files",
        "claude-root-cause",
        "claude-scope",
        "claude-verification",
        "claude-xml",
        "fable5-ground-progress",
        "fable5-no-show-thinking",
        "fable51-drop-antiformatting",
        "fable51-finish-whole-task",
        "fable51-mannered-prose",
        "fable51-scope-changes",
        "opus48-encourage-subagents",
        "opus5-concise",
        "opus5-remove-verification",
        "opus5-report-all",
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
    "Обязательно почини баг в @a.py. Обязательно прогони тесты.",
    "Сделай бэкап базы. Сделай бэкап базы.",
    "Почини @a.py. Почини @a.py. И прогони тесты.",
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


def test_числа_в_документации_совпадают_с_фактом():
    """Доки расходились с кодом шесть кругов подряд, и каждый раз — в одной из
    двух языковых половин. Числа теперь проверяются, а не переписываются руками.
    """
    import io
    import os
    import re

    корень = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    правил = sum(len(catalog.load_family(f)["rules"]) for f in ВСЕ_СЕМЕЙСТВА)
    страниц = sum(
        # Считаем ТЕМ ЖЕ вызовом, что и сам `update`, а не своей формулой.
        # Своя давала 22 (только `docs`), команда качала 24 (плюс `index`
        # каждого семейства) — и в договоре двадцать один круг стояло число,
        # которое не совпадало ни с чем. Проверка, считающая иначе, чем код,
        # проверяет собственную арифметику.
        1 for _ in _all_urls()
    )
    for имя in ("CLAIMS.md", "CLAIMS.ru.md"):
        текст = io.open(os.path.join(корень, имя), encoding="utf-8").read()
        # Границы слова обязательны: без них «26» находилось внутри «2026», и
        # мутация «26 rules → 24 rules» проходила зелёной.
        assert re.search(r"\b%d\b" % правил, текст), (
            "%s: не упомянуто фактическое число правил %d" % (имя, правил)
        )
        числа = set(re.findall(r"(\d+) (?:canonical|канонических)", текст))
        assert not числа - {str(страниц)}, (
            "%s: заявлено %s канонических страниц, в манифесте %d" % (имя, числа, страниц)
        )
        # Раскладка обязана сходиться с итогом. Именно эта пара разъезжалась
        # чаще всего: «150 passed» строкой выше и сумма 63 строкой ниже.
        итог = re.search(r"# (\d+) passed", текст)
        раскладка = re.search(r"#   (\d+ [^\n]+)", текст)
        if итог and раскладка:
            слагаемые = [int(x) for x in re.findall(r"(\d+) ", раскладка.group(1) + " ")]
            assert sum(слагаемые) == int(итог.group(1)), (
                "%s: раскладка %s = %d, а заявлено %s"
                % (имя, слагаемые, sum(слагаемые), итог.group(1))
            )


def test_readme_не_расходится_с_числом_страниц():
    """Круг 22: CLAIMS исправили с 22 на 24, README — нет.

    «(из N)» в примере вывода — это total, он всегда равен числу URL в
    манифесте и от сети не зависит, значит проверяется точно.
    """
    import io
    import re as _re
    from nativeprompt.update import _all_urls

    сколько = len(_all_urls())
    for имя in ("README.md", "README.en.md"):
        текст = io.open(имя, encoding="utf-8").read()
        for m in _re.finditer(r"\(из (\d+)\)|\(of (\d+)\)", текст):
            число = m.group(1) or m.group(2)
            assert int(число) == сколько, (
                "%s: пример показывает «из %s», манифест даёт %d" % (имя, число, сколько))


def test_русский_readme_перечисляет_все_флаги_update():
    """Круг 22: `--diff` был в CLAIMS обоих языков и в англ. README, но не в русском."""
    import io
    from nativeprompt.__main__ import build_parser

    подкоманды = build_parser()._subparsers._group_actions[0].choices
    флаги = {д for д in подкоманды["update"]._option_string_actions if д.startswith("--")}
    текст = io.open("README.md", encoding="utf-8").read()
    строка = [l for l in текст.split("\n") if "Флаги `update`" in l]
    assert строка, "исчезла строка про флаги update"
    for флаг in флаги - {"--help"}:
        assert флаг in строка[0], "%s не назван в README.md" % флаг


def test_claims_не_врёт_про_размер_собственного_файла():
    """Круг 23: CLAIMS обещал «62 теста в tests/test_rules.py», их было 64.

    Разбивка по файлам в разделе «Проверяемость» уже сверялась автоматически,
    а эта строчка жила отдельно и руками — и разошлась.
    """
    import io
    import re as _re
    import subprocess
    import sys
    from collections import Counter

    собрано = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"],
                             capture_output=True, text=True)
    счёт = Counter(l.split("::")[0].split("/")[-1]
                   for l in собрано.stdout.splitlines() if "::" in l)
    сколько = счёт["test_rules.py"]
    # `тест\w*` вместо жёсткого «теста»: число тестов управляет падежом («65
    # теста», но «90 тестов»), и прежний шаблон требовал написать безграмотно
    # либо получить «пропала строчка» на верной цифре.
    for имя, шаблон in (("CLAIMS.ru.md", r"(\d+) тест\w* в `tests/test_rules\.py`"),
                        ("CLAIMS.md", r"(\d+) tests in `tests/test_rules\.py`")):
        текст = io.open(имя, encoding="utf-8").read()
        m = _re.search(шаблон, текст)
        assert m, "пропала строчка про число тестов в %s" % имя
        assert int(m.group(1)) == сколько, (
            "%s обещает %s тестов в test_rules.py, собрано %d" % (имя, m.group(1), сколько))


def test_claims_не_врёт_ни_про_один_счётчик_тестов():
    """Круг 27: сторож был только у test_rules.py, остальные цифры жили руками.

    Класс дефекта известный: тест сторожит потолок, а опубликованное рядом
    число тихо расходится с кодом. Ровно так же здесь: после каждого нового
    теста все опубликованные числа становились неверными, и заметить это мог
    только человек, который решит их пересчитать.

    Проверяется общее число и разбивка по каждому файлу — в обеих языковых
    версиях сразу.
    """
    import io
    import re as _re
    import subprocess
    import sys
    from collections import Counter

    собрано = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q"],
                             capture_output=True, text=True)
    строки = [l for l in собрано.stdout.splitlines() if "::" in l]
    счёт = Counter(l.split("::")[0].split("/")[-1] for l in строки)
    всего = len(строки)

    for имя in ("CLAIMS.md", "CLAIMS.ru.md", "README.md", "README.en.md"):
        текст = io.open(имя, encoding="utf-8").read()

        # Разбивка: «NNN тестов в `tests/<файл>.py`» на любом языке.
        for m in _re.finditer(r"(\d+)\s+(?:тест\w*|tests?)\s+(?:в|in)\s+`tests/(test_[a-z_]+\.py)`", текст):
            обещано, файл = int(m.group(1)), m.group(2)
            assert обещано == счёт[файл], (
                "%s обещает %d тестов в %s, собрано %d"
                % (имя, обещано, файл, счёт[файл]))

        # Общее число: «NNN тестов» рядом со словом-маркером, чтобы не ловить
        # посторонние числа вроде «527 мутаций».
        for m in _re.finditer(r"(\d{3,5})\s+(?:тест\w*|tests)\b(?![^\n]*`tests/)", текст):
            число = int(m.group(1))
            # Счётчиком считаем только то, что похоже на общий итог: остальные
            # трёхзначные числа в тексте это не про наш прогон.
            if abs(число - всего) <= 400 or число == всего:
                assert число == всего, (
                    "%s обещает %d тестов всего, собрано %d" % (имя, число, всего))


# ── двадцать шестой круг: цена ложного срабатывания ───────────────────
#
# CLAIMS честно признаёт: детекторы здесь — регулярки, и часть находок ложные.
# Но хук подмешивает разбор на КАЖДЫЙ промпт и заканчивает строкой «Действуй по
# улучшенной версии» — то есть по ложной находке модель получает поручение.
# Живой случай: «почини это» на тридцатом сообщении отладочной сессии. Промпт
# понятный, файл назван двадцать сообщений назад, а детектор истории не видит и
# требует заскоупить задачу.
#
# Делать детектор точнее проект пробовал восемь кругов подряд — дорога без
# конца. Дешевле другое: рядом с каждым советом печатать КОНКРЕТНУЮ ситуацию,
# в которой он не применяется: «если это не про вас — не обращайте внимания».
# Тогда ложное срабатывание ничего не стоит.
#
# Здесь проверяется само поле и его дорога до всех трёх выходов инструмента.

#: Действия, у которых оговорка ОБЯЗАТЕЛЬНА. `warn` и `restructure` — это
#: чистый совет человеку: текст инструмент не трогает (warn) или предлагает
#: переформулировать (restructure), и цена ошибки здесь целиком на читателе.
ДЕЙСТВИЯ_С_ОГОВОРКОЙ = {"warn", "restructure"}

#: Условия, которые ничего не сообщают: «если сомневаетесь», «если это не ваш
#: случай». Задание требует КОНКРЕТНУЮ ситуацию неприменимости, а не общее
#: сомнение, — а общее сомнение прячется как раз за такими оборотами и проходит
#: и по длине, и по наличию слова «если».
ПУСТЫЕ_УСЛОВИЯ = (
    "если сомневаетесь", "если это не ваш случай", "если не подходит",
    "если совет не подходит", "если вам виднее", "если не уверены",
)


def _правила(family):
    return catalog.load_family(family)["rules"]


def _все_правила():
    return [(f, r) for f in ВСЕ_СЕМЕЙСТВА for r in _правила(f)]


@pytest.mark.parametrize("family", ВСЕ_СЕМЕЙСТВА)
def test_совет_человеку_идёт_с_границей_неприменимости(family):
    """У каждого `warn` и `restructure` — поле `unless`, и оно осмысленно.

    Осмысленность проверяется механически, иначе тест закрывается пустой
    строкой-заглушкой: длина, названное условие («если» / «когда»), и то, что
    это не пересказ `why` другими словами.
    """
    for r in _правила(family):
        if r["action"] not in ДЕЙСТВИЯ_С_ОГОВОРКОЙ:
            continue
        оговорка = (r.get("unless") or "").strip()
        assert len(оговорка) > 20, "%s/%s: пустая или куцая unless" % (family, r["id"])
        assert len(оговорка.split()) >= 8, (
            "%s/%s: оговорка короче фразы — ситуацию так не назовёшь" % (family, r["id"]))
        assert re.search(r"\b(если|когда)\b", оговорка, re.I), (
            "%s/%s: оговорка без названного условия — это общее сомнение"
            % (family, r["id"]))
        assert оговорка not in (r["why"], r["title"]), (
            "%s/%s: оговорка повторяет правило, а не ограничивает его"
            % (family, r["id"]))
        низ = оговорка.lower()
        for пусто in ПУСТЫЕ_УСЛОВИЯ:
            assert пусто not in низ, (
                "%s/%s: «%s» — не ситуация, а общее сомнение" % (family, r["id"], пусто))


def test_оговорка_не_шаблон_ради_теста():
    """Защита от вырождения: одна и та же оговорка у всех правил — это шаблон.

    Совпади текст у двух правил — он написан про инструмент вообще, а не про
    границу конкретного совета, и толку от него читателю нет. Отдельно
    проверяется начало фразы: шаблон обычно копируют целиком и правят хвост.
    """
    from collections import Counter

    оговорки = [(f, r["id"], (r.get("unless") or "").strip())
                for f, r in _все_правила() if r.get("unless")]
    assert len(оговорки) >= 16, "оговорок стало меньше, чем правил-советов"
    счёт = Counter(т for _, _, т in оговорки)
    повторы = [т for т, n in счёт.items() if n > 1]
    assert not повторы, "одна оговорка на несколько правил: %s" % повторы[:2]
    начала = Counter(т[:24] for _, _, т in оговорки)
    частое, сколько = начала.most_common(1)[0]
    assert сколько <= 2, "%d оговорок начинаются одинаково (%r) — это шаблон" % (
        сколько, частое)


@pytest.mark.parametrize("family", ВСЕ_СЕМЕЙСТВА)
def test_у_каждого_правила_есть_приоритет(family):
    """1 — контракт результата и границы задачи, 2 — режим запуска и структура,
    3 — косметика. Без поля порядок находок — это порядок строк в файле."""
    for r in _правила(family):
        assert r.get("priority") in {1, 2, 3}, (
            "%s/%s: priority %r вне {1,2,3}" % (family, r["id"], r.get("priority")))


def test_приоритеты_не_вырождены():
    """Все три уровня заняты. Иначе сортировка есть, а порядка от неё нет."""
    from collections import Counter

    счёт = Counter(r["priority"] for _, r in _все_правила())
    assert set(счёт) == {1, 2, 3}, "уровни приоритета использованы не все: %s" % dict(счёт)
    for уровень in (1, 2, 3):
        assert счёт[уровень] >= 2, "уровень %d занят одним правилом" % уровень


def test_оговорка_и_приоритет_доезжают_до_находки():
    """Поле в JSON, которое не доходит до находки, — мёртвый груз."""
    from nativeprompt.explain import build_report

    r = build_report("Не мог бы ты пожалуйста ОБЯЗАТЕЛЬНО починить баг в логине, "
                     "думай пошагово и обязательно перепроверь себя. "
                     "Покажи только самое важное.", "claude-opus-5")
    правила = {rr["id"]: rr for rr in _правила("claude")}
    assert r["findings"]
    for f in r["findings"]:
        assert f["unless"] == правила[f["id"]]["unless"], f["id"]
        assert f["priority"] == правила[f["id"]]["priority"], f["id"]


@pytest.mark.parametrize("model", ["claude-opus-5", "claude-fable-5", "gpt-5.6"])
def test_находки_идут_от_важного_к_косметике(model):
    """Порядок находок больше не повторяет порядок строк в файле правил.

    До этого круга «нет контракта результата» могло встать ниже совета убрать
    КАПС — просто потому, что правило записано ниже. Человек читает сверху
    вниз и первым правит то, что напечатано первым.
    """
    from nativeprompt.explain import build_report

    for prompt in КОРПУС_ДЛЯ_НОЖЕЙ:
        находки = build_report(prompt, model)["findings"]
        приоритеты = [f["priority"] for f in находки]
        assert приоритеты == sorted(приоритеты), (prompt, [f["id"] for f in находки])


@pytest.mark.parametrize("model", ["claude-opus-5", "claude-fable-5", "gpt-5.6"])
def test_сортировка_стабильна_внутри_приоритета(model):
    """Сортировка меняет ОЧЕРЕДЬ, а не набор: внутри одного приоритета остаётся
    порядок файла правил. Иначе одинаково важные советы каждый раз тасовались бы
    по внутреннему признаку, и вывод перестал бы быть воспроизводимым."""
    from nativeprompt.explain import build_report

    for prompt in КОРПУС_ДЛЯ_НОЖЕЙ:
        отчёт = build_report(prompt, model)
        место = {r["id"]: i for i, r in enumerate(_правила(отчёт["target"]["family"]))}
        находки = отчёт["findings"]
        assert {f["id"] for f in находки} <= set(место)
        for a, b in zip(находки, находки[1:]):
            if a["priority"] == b["priority"]:
                assert место[a["id"]] < место[b["id"]], (prompt, a["id"], b["id"])


def test_контракт_результата_печатается_выше_косметики():
    """Пин на живой промпт из examples/prompts.md.

    `opus5-report-all` (сузили выдачу — получите не всё) записан в файле ПОСЛЕ
    `claude-dial-caps` (снять КАПС). Без сортировки косметика шла первой.
    """
    from nativeprompt.explain import build_report

    находки = build_report(
        "Не мог бы ты пожалуйста ОБЯЗАТЕЛЬНО починить баг в логине, думай пошагово "
        "и обязательно перепроверь себя. Покажи только самое важное.",
        "claude-opus-5")["findings"]
    ids = [f["id"] for f in находки if not f["always"]]
    assert {"opus5-report-all", "claude-dial-caps"} <= set(ids), ids
    assert ids.index("opus5-report-all") < ids.index("claude-dial-caps"), ids


def _без_переносов(текст):
    """Отчёт переносит длинные строки по словам — сравниваем по словам."""
    return " ".join(текст.split())


def test_оговорка_печатается_рядом_с_находкой():
    """Первый из трёх выходов: отчёт на экране."""
    from nativeprompt.explain import build_report, render_report

    отчёт = build_report("Не мог бы ты починить баг в логине", "claude-opus-5")
    экран = _без_переносов(render_report(отчёт))
    assert "неприменимо:" in экран
    for f in отчёт["findings"]:
        assert _без_переносов(f["unless"]) in экран, f["id"]


def test_оговорка_уезжает_в_метапромпт():
    """Второй выход: инструкция вашей же модели.

    Мета-промпт — единственное место, где правила читает не человек, а модель;
    без оговорки она применит совет буквально, потому что её об этом попросили.
    """
    from nativeprompt.explain import build_report

    отчёт = build_report("Не мог бы ты починить баг в логине", "claude-opus-5")
    мета = отчёт["metaprompt"]
    assert "Неприменимо:" in мета
    for f in отчёт["findings"]:
        assert f["unless"] in мета, f["id"]
    # И сказано, что с этим делать: правило можно отвергнуть по делу.
    assert "пропусти" in мета and "не приказ" in мета


def test_оговорка_доходит_до_хука():
    """Третий выход, и самый важный: хук работает на КАЖДОМ промпте и истории
    диалога не видит. Проверяем через настоящий запуск, а не импортом функции:
    у людей в settings.json прописан именно этот файл."""
    import json
    import os
    import subprocess
    import sys

    корень = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    среда = dict(os.environ, ANTHROPIC_MODEL="claude-opus-5")
    готово = subprocess.run([sys.executable, os.path.join(корень, "hooks",
                                                          "nativeprompt_hook.py")],
                            input=json.dumps({"prompt": "Не мог бы ты починить баг в логине"}),
                            capture_output=True, text=True, cwd=корень, env=среда)
    assert готово.stdout.strip(), готово.stderr[:400]
    контекст = json.loads(готово.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "неприменимо:" in контекст, контекст[:400]
    правила = {r["id"]: r for r in _правила("claude")}
    assert правила["claude-scope"]["unless"] in контекст, контекст[:400]
    # И оговорка объяснена: совет можно не применять, это не поручение.
    assert "совет пропусти" in контекст
