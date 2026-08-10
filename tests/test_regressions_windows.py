"""Регрессии из внешнего отчёта (Windows, Claude Code, opus-5).

Каждый тест здесь — воспроизведённая жалоба живого пользователя. Свои тесты я
писал на однострочных промптах без разметки и без имён собственных, поэтому ни
одна из этих поломок не ловилась: проверялось только то, что нужное удалилось,
и ни разу — что остальное уцелело.
"""

from __future__ import annotations

import io
import os

import json
import os
import subprocess
import sys

from nativeprompt.analyze import analyze, task_shape
from nativeprompt.harness import recommend_harness
from nativeprompt.rewrite import _soften_caps, _tidy

CLAUDE = {"family": "claude", "generation": "opus-5"}


def ids_for(prompt, model):
    """Идентификаторы сработавших правил для произвольной модели."""
    from nativeprompt.explain import build_report

    return {f["id"] for f in build_report(prompt, model)["findings"] if not f["always"]}


def _код(prompt):
    """Сработали ли правила, требующие контекста/проверки, — признак кодовой задачи."""
    return bool({"claude-scope", "claude-verification"} & ids(prompt))


def ids(prompt):
    return {f["id"] for f in analyze(prompt, CLAUDE) if not f["always"]}


# ── порча текста ────────────────────────────────────────────────────
def test_имя_собственное_не_разрывается_точкой():
    """«планировщик Windows» → «планировщик. Windows» — из отчёта, дословно.

    Эвристика склеек не может отличить начало предложения от имени собственного.
    Регрессия про середину текста, не про заглавную: `_tidy` теперь только
    добавляет точку в конце и капитализацию больше не делает сама — это
    забрала на себя `_strip_vague` там, где она снимает вежливую обёртку.
    """
    assert _tidy("настрой планировщик Windows") == "настрой планировщик Windows."
    assert _tidy("обзор рынка в России") == "обзор рынка в России."
    assert _tidy("проверь через Docker и Redis") == "проверь через Docker и Redis."


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


#: Обычные слова, которые НЕ должны считаться признаком задачи по коду.
#: Список намеренно широкий: один корень проверить мало — первая редакция фикса
#: поставила границу слова только там, где я заметил проблему, и «тест» продолжал
#: находиться внутри «аттестации», а «класс» внутри «классический».
СЛОВАРЬ_НЕ_КОД = """
положение аттестации методику методика методология классный классический классическую
классика кампании описание сценарий сценария запрос запросить схематично билет ветеран
скриптор тестостерон апрель апартаменты функционер функционал модуляция схематика
статья политика компания страница рынок отчёт таблица источник конкурент тесто
testimony classical scripture apiary building buildings methodology description testes
""".split()

СЛОВАРЬ_КОД = """
функция функции метод методы класс классы модуль модули скрипт скрипты тест тесты
схема схемы баг баги ветка апи сборка билд эндпоинт роут компонент миграция
репозиторий коммит парсер валидация хендлер конфиг деплой ошибка api endpoint parser
тестов тестами тестах багом багов методов методам классах классами модулях модулей
функциях функциями схемах ветками сборках апи билдов
queries query tests testing builds endpoints classes modules parsers apis bugs
""".split()


def test_ни_один_корень_не_ловится_внутри_обычного_слова():
    """Сканер по словарю, а не проверка одного корня.

    «апи» находилось внутри «н-апи-ши», «тест» внутри «аттестации», «класс» внутри
    «классический». Правило чинилось дважды, потому что первый раз проверялся один
    корень из сорока. Тест обязан идти по всему списку.
    """
    from nativeprompt.analyze import _CODE_NOUN

    ложные = [w for w in СЛОВАРЬ_НЕ_КОД if _CODE_NOUN.search(w)]
    assert not ложные, f"обычные слова приняты за код: {ложные}"
    assert not _CODE_NOUN.search("напиши разбор")


def test_настоящие_корни_кода_не_потеряны():
    """Обратный контроль: сузив регулярку, легко выключить её целиком."""
    from nativeprompt.analyze import _CODE_NOUN

    пропущено = [w for w in СЛОВАРЬ_КОД if not _CODE_NOUN.search(w)]
    assert not пропущено, f"перестали распознаваться как код: {пропущено}"


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


# ── находки повторного ревью (Fable 5, чистый контекст) ─────────────
def test_смешанный_verify_режет_только_голую_фразу():
    """Детектор и нож должны быть одним кодом, а не двумя регулярками.

    Детектор научили щадить фразу с требованием к результату, а strip в rewrite
    остался глобальным — и на промпте, где рядом защищённая и голая фразы,
    вырезались обе. Условие «Если не всплывёт» снова повисало в пустоте.
    """
    from nativeprompt.explain import build_report

    p = ("Почини баг в @src/parse.py и прогони тесты. Убедись, что признак всплывает "
         "на трудном случае. Если не всплывёт — признай метод дырявым. "
         "В самом конце перепроверь себя ещё раз.")
    out = build_report(p, "claude-opus-5")["improved"]
    assert "Убедись, что признак всплывает" in out, "срезали защищённую фразу"
    assert "Если не всплывёт" in out, "условие осталось без своего звена"
    # Голую фразу тоже больше не режем: см. test_verification_demand_показывается…
    assert "перепроверь себя" in out, "инструмент снова уничтожает содержимое"


def test_две_просьбы_через_союз_не_считаются_защитой():
    """«перепроверь себя И покажи дифф» — два дела, а не результат проверки."""
    assert "opus5-remove-verification" in ids("перепроверь себя и покажи финальный дифф")


def test_заказанный_результат_не_исчезает_из_переписи():
    """Ревью поймало: детектор считал «покажи дифф» отдельной просьбой,
    а нож всё равно вырезал предложение целиком вместе с ней."""
    from nativeprompt.explain import build_report

    out = build_report(
        "Почини баг в @src/auth.py и прогони тесты. Перепроверь себя и покажи финальный дифф.",
        "claude-opus-5",
    )["improved"]
    assert "покажи финальный дифф" in out


def test_реальный_шаг_задачи_не_вырезается():
    """«Прогони линтер, а также убедись, что нет warnings» — целиком исчезало."""
    from nativeprompt.explain import build_report

    out = build_report(
        "Отрефактори @src/utils.py. Прогони линтер, а также убедись, что нет warnings",
        "claude-opus-5",
    )["improved"]
    assert "Прогони линтер" in out


def test_фраза_внутри_кода_не_считается_просьбой():
    """Детектор и переписчик обязаны видеть один текст.

    `msg = "перепроверь себя"` внутри блока кода — это данные для вставки,
    а не обращение к модели: предупреждение о нём было ложным.
    """
    p = 'Вставь строку:\n```python\nmsg = "перепроверь себя и попробуй снова"\n```'
    assert "opus5-remove-verification" not in ids(p)


def test_висящий_союз_не_срезается_в_начале_строки():
    """Правило писалось для шва после вырезания; построчно оно съедало смысл.

    «Но не трогай конфиг прода» теряло противопоставление — правка вдали от
    места вырезания, тот же класс, что и удалённая эвристика склеек.
    """
    src = "Важно: одна правка.\nНо не трогай конфиг прода.\nИ не коммить без спроса."
    got = _tidy(src)
    assert "Но не трогай" in got
    assert "И не коммить" in got


def test_блок_кода_не_правится():
    """Инструмент молча менял строковый литерал внутри чужой программы."""
    from nativeprompt.rewrite import outside_code

    src = 'ВАЖНО: поправь.\n```python\nprint("ВАЖНО: не трогать")\n```'
    got = outside_code(_soften_caps, src)
    assert 'print("ВАЖНО: не трогать")' in got, "чистка залезла в код"
    assert got.startswith("Важно:"), "снаружи блока чистка не сработала"


def test_таблица_и_отступ_сохраняют_пробелы():
    src = "Итог:\n| колонка   | значение |\n    отступ  сохраняется"
    got = _tidy(src)
    assert "| колонка   | значение |" in got, "схлопнули выравнивание таблицы"
    assert "    отступ  сохраняется" in got, "схлопнули отступ блока кода"


def test_кодовая_задача_со_словом_исследование_не_глушится():
    """Гейт разведки не должен подавлять законные правила у задачи про код."""
    got = ids("Проведи исследование бага в парсере и исправь причину")
    assert "claude-scope" in got and "claude-verification" in got


def test_правка_со_спецификацией_не_считается_пустяком():
    p = "Подправь расчёт комиссии в биллинге: округление вверх, потолок 500 рублей"
    assert task_shape(p) == "normal"


def test_совет_по_форме_одинаков_у_всех_семейств():
    """Ветку `normal` описали двое из шести; остальные откатывались на `trivial`.

    Дефолт для неопознанной формы обязан жить в коде, иначе каждое новое
    семейство молча наследует чужой уверенный совет.
    """
    research = "Сделай обзор рынка за 2026 год с тремя таблицами и списком источников."
    for family in ("claude", "openai", "gemini", "qwen", "kimi", "grok"):
        rec = recommend_harness(research, {"family": family})
        assert rec["shape"] == "normal"
        assert "не определилась" in rec["title"], f"{family}: {rec['title']}"


def test_защита_кода_включена_в_самом_пайплайне():
    """Прошлый тест звал outside_code напрямую и не ловил её отключение.

    Мутация «убрать все обёртки outside_code из rewrite()» проходила все 92
    теста: проверялась функция, а не то, что её кто-то использует.
    """
    from nativeprompt.explain import build_report

    p = ('ВАЖНО: поправь вывод.\n```python\nprint("ВАЖНО: не трогать")\n```\n'
         'Не мог бы ты заодно убрать `MUST` из шаблона?')
    out = build_report(p, "claude-opus-5")["improved"]
    assert 'print("ВАЖНО: не трогать")' in out, "чистка залезла в блок кода"
    assert "`MUST`" in out, "чистка залезла в инлайн-код"
    assert "Важно: поправь вывод" in out, "снаружи кода чистка не сработала"


def test_незакрытый_блок_кода_тоже_защищён():
    from nativeprompt.rewrite import outside_code

    got = outside_code(_soften_caps, 'СРОЧНО поправь.\n```python\nprint("СРОЧНО: не менять")')
    assert 'print("СРОЧНО: не менять")' in got
    assert got.startswith("Срочно поправь.")


# ── находки третьего круга ревью ────────────────────────────────────
def test_код_в_промпте_цел_когда_ни_одно_правило_не_сработало():
    """Худший дефект из найденных: инструмент ломал Python в промпте.

    Ветка «ничего не вырезали» схлопывала двойные пробелы в обход `outside_code`
    и построчной защиты, и отступы блока превращались в один пробел. Путь самый
    частый — когда ни одна чистка не срабатывает. Ирония: промпт с «ОБЯЗАТЕЛЬНО»
    был безопаснее вежливого, потому что там включался `_tidy`.
    """
    from nativeprompt.explain import build_report

    p = ("Объясни, что делает эта функция:\n```python\ndef f(x):\n"
         "    if x:\n        return 1\n    return 0\n```")
    out = build_report(p, "claude-opus-5")["improved"]
    assert "    if x:" in out and "        return 1" in out, "отступы схлопнуты, код сломан"


def test_меняющий_глагол_перебивает_маркер_разведки():
    """Зеркальная ошибка гейта разведки: он глушил кодовые задачи.

    «конкурентный доступ» в русском — про параллелизм, а не про рынок, и
    «исправь баг конкурентного доступа и сравни результаты» оставалось совсем
    без правил.
    """
    for p in ("Исправь баг конкурентного доступа к кэшу и сравни результаты до и после",
              "Сравни цену вычисления в функции compute_price и оптимизируй код",
              "Проведи исследование бага в парсере и исправь причину"):
        got = ids(p)
        assert "claude-scope" in got or "claude-verification" in got, p
    # Случай, где решает именно меняющий глагол: сильный маркер разведки
    # («обзор рынка … конкурентов») тут срабатывает, и без гейта задача целиком
    # уходила бы в разведку вместе с «исправь баг в парсере».
    смешанный = "Сделай обзор рынка наших конкурентов и исправь баг в парсере цен"
    assert {"claude-scope", "claude-verification"} & set(ids(смешанный)), смешанный

    # Обратный контроль: настоящая разведка по-прежнему не требует файла.
    assert not ({"claude-scope", "claude-verification"} & set(
        ids("Сделай обзор рынка API-шлюзов и сравни цены на тарифы")))


def test_сильный_признак_пустяка_не_боится_перечисления():
    """Список опечаток — это по-прежнему опечатки, а не спецификация."""
    assert task_shape("Исправь опечатки: «превет», «сонце», «малако»") == "trivial"
    assert task_shape("Исправь опечатку: «превет» → «привет»") == "trivial"
    # А слабый признак уступает любой спецификации после двоеточия.
    assert task_shape("Подправь расчёт комиссии: округляй вверх до потолка 500") == "normal"
    assert task_shape("Подправь отступ в шапке") == "trivial"


def test_глагол_выдачи_защищает_только_в_своём_предложении():
    """Окно защиты перепрыгивало точку и гасило совершенно голую просьбу."""
    assert "opus5-remove-verification" in ids(
        "Почини @a.py и прогони тесты. Перепроверь себя. Покажи итоговый статус.")
    # А последствие живёт отдельным предложением — ему окно нужно широкое.
    assert "opus5-remove-verification" not in ids(
        "Убедись, что признак всплывает. Если не всплывёт — признай метод дырявым.")


def test_незакрытый_блок_маскируется_и_для_детектора():
    """Две регулярки под одним именем разошлись: rewrite знал, analyze нет."""
    from nativeprompt.analyze import CODE_SPAN
    from nativeprompt.rewrite import _CODE_SPAN

    assert CODE_SPAN is _CODE_SPAN, "снова две разные регулярки кода"
    assert "opus5-remove-verification" not in ids(
        'Вставь в конец файла:\n```python\nmsg = "перепроверь себя и попробуй снова"')


def test_форма_задачи_считается_по_тому_же_тексту_что_и_правила():
    """Отчёт противоречил сам себе: shape=trivial и правила, гасимые на trivial."""
    from nativeprompt.explain import build_report

    r = build_report("Почини функцию:\n```\ndef typo(): pass\n```", "claude-opus-5")
    fired = {f["id"] for f in r["findings"] if not f["always"]}
    if r["shape"] == "trivial":
        assert not ({"claude-scope", "claude-verification"} & fired), "shape и правила разошлись"


def test_действие_правила_в_json_соответствует_поведению_кода():
    """Пин против расхождения данных и кода.

    Если кто-то вернёт `action: remove` в JSON, отчёт начнёт рисовать «[-] Убрать»,
    а текст останется нетронутым — инструмент будет обещать правку, которой нет.
    """
    from nativeprompt import catalog

    data = catalog.load_family("claude")
    rule = next(r for r in data["rules"] if r["id"] == "opus5-remove-verification")
    assert rule["action"] == "warn", (
        "правило снова помечено как удаляющее, но ветки вырезания в rewrite нет"
    )


def test_совет_по_режиму_никогда_не_откатывается_на_чужую_ветку():
    """Недостающая ветка не должна превращаться в уверенный совет."""
    from nativeprompt.harness import recommend_harness

    rec = recommend_harness("что-то неопознанное", {"family": "kimi"}, shape="planning")
    assert rec is not None
    fake = recommend_harness("x", {"family": "kimi"}, shape="нет-такой-формы")
    assert "не определилась" in fake["title"]


def test_советы_в_любой_момент_не_теряются():
    """Три сорсенных совета вендора не показывались никогда: словарь их схлопывал."""
    from nativeprompt.harness import recommend_harness

    rec = recommend_harness("Напиши парсер логов", {"family": "grok"})
    cmds = {c["command"] for c in rec["anytime"]}
    assert {"/effort", "/rewind"} <= cmds, cmds


# ── находки четвёртого круга: ножи, безопасные по построению ────────
def test_softcaps_только_понижает_регистр():
    """Единственная операция, которая не может сломать смысл, — регистр.

    Всё остальное здесь уже пробовали и всё ломалось: удаление слова
    обезглавливало абзац, удаление MUST превращало требование в утверждение
    факта («Tests MUST pass» → «Tests pass»), подстановка вставляла русское
    «нужно» в английский текст и давала аграмматичное «нужно почини».
    """
    from nativeprompt.rewrite import _soften_caps

    # «Tests MUST pass» больше НЕ понижается: английские слова-усилители сплошь
    # и рядом бывают техническим значением (уровень лога, значение конфига,
    # HTTP-метод), а по форме крик от значения не отличить. Понижаем их только
    # когда стоят заголовком — за ними двоеточие или восклицательный знак.
    assert _soften_caps("Tests MUST pass") == "Tests MUST pass"
    assert _soften_caps("IMPORTANT: fix it") == "Important: fix it"
    assert _soften_caps("ОБЯЗАТЕЛЬНО почини") == "Обязательно почини"
    assert _soften_caps("ВАЖНО: соблюдай рамки") == "Важно: соблюдай рамки"
    assert _soften_caps("Ты ДОЛЖЕН починить") == "Ты должен починить"
    # Ни одно слово не пропало и не заменилось на другое.
    for src in ("Tests MUST pass", "ОБЯЗАТЕЛЬНО почини", "ВАЖНО: рамки"):
        assert len(_soften_caps(src).split()) == len(src.split()), src


def test_чистка_не_давит_код_ни_в_каком_виде():
    """У `_tidy` был свой список защищённого, и он разошёлся с общей картой кода."""
    from nativeprompt.explain import build_report

    r = build_report("ОБЯЗАТЕЛЬНО почини баг в @src/a.py и прогони тесты.\n"
                     "~~~python\nx  =  1\n~~~", "claude-opus-5")
    assert "x  =  1" in r["improved"], "код в ~~~ схлопнут"
    r2 = build_report("ОБЯЗАТЕЛЬНО почини `x  =  1` в @src/a.py и прогони тесты",
                      "claude-opus-5")
    assert "`x  =  1`" in r2["improved"], "инлайн-код схлопнут"


def test_вежливость_снимается_только_в_начале():
    """`_strip_vague` не имел ни одного пина, а он тоже меняет текст."""
    from nativeprompt.rewrite import _strip_vague

    # Заглавную не ставим: остаток часто начинается с регистрозависимого токена
    # («npm ci», «src/utils.py», «git push»), и косметика ломала команду.
    assert _strip_vague("Не мог бы ты починить @a.py") == "починить @a.py"
    # В середине фразы оборот не трогаем: там он может быть частью смысла.
    src = "Спроси у команды, можешь ли ты трогать прод"
    assert _strip_vague(src) == src


def test_детектор_цепочки_не_шире_ножа():
    """Отчёт печатал «[-] Убрать» на «Опиши пошагово», хотя нож её не трогает."""
    assert "codex-no-forced-cot" not in ids_for("Опиши пошагово процесс деплоя в @docs/deploy.md",
                                                "gpt-5.6")
    assert "codex-no-forced-cot" in ids_for("Реализуй парсер, думай пошагово", "gpt-5.6")


def test_предмет_обзора_не_путается_с_предметом_работы():
    """«обзор рынка API-шлюзов» — исследование, «создай скрипт» — работа."""
    assert not _код("Сделай обзор рынка API-шлюзов и сравни цены на тарифы")
    assert not _код("Проведи анализ рынка парсеров логов и добавь выводы в конспект")
    assert _код("Сделай обзор рынка и создай скрипт сбора цен конкурентов")


def test_сильный_признак_пустяка_уступает_второму_делу():
    """«переименуй колонку … и напиши миграцию» — уже не опечатка."""
    assert task_shape("Переименуй колонку user_id в account_id в БД и напиши миграцию") == "normal"
    # Дословно из отчёта: прошлый пин был написан на удлинённой строке, которая
    # переползала порог длины, — то есть подогнан под фикс, а не под жалобу.
    assert task_shape("добавь логирование с ротацией и маскированием PII") == "normal"
    assert task_shape("Добавь логирование всех запросов с ротацией и маскированием PII") == "normal"
    assert task_shape("Переименуй переменную old в new") == "trivial"


def test_чистка_не_съедает_пробел_перед_инлайн_кодом():
    """`outside_code` кормит чистку обрезками, кончающимися посреди строки.

    Прежний `rstrip()` съедал пробел на таком краю, и слово слипалось с кодом.
    Фикс защиты кода сам породил новую порчу того же класса.
    """
    from nativeprompt.explain import build_report

    out = build_report("СРОЧНО почини `run_all()` и прогони тесты в @b.py", "claude-opus-5")
    assert "почини `run_all()`" in out["improved"], out["improved"]


def test_чистка_не_переформатирует_данные_пользователя():
    """Схлопывание двойных пробелов — не шов, а вкусовщина, и оно портило данные."""
    from nativeprompt.rewrite import _tidy

    assert '"строку 1  2"' in _tidy('ОБЯЗАТЕЛЬНО заменить "строку 1  2"')


def test_регистр_не_лезет_в_ссылки_и_имена_файлов():
    """«Регистр не может сломать смысл» — верно до первого регистрозависимого токена."""
    from nativeprompt.rewrite import _soften_caps

    assert _soften_caps("см. https://EXAMPLE.com/MUST-READ") == "см. https://EXAMPLE.com/MUST-READ"
    assert _soften_caps("открой MUST-README.md") == "открой MUST-README.md"
    # А обычное слово по-прежнему понижается.
    # «Tests MUST pass» больше НЕ понижается: английские слова-усилители сплошь
    # и рядом бывают техническим значением (уровень лога, значение конфига,
    # HTTP-метод), а по форме крик от значения не отличить. Понижаем их только
    # когда стоят заголовком — за ними двоеточие или восклицательный знак.
    assert _soften_caps("Tests MUST pass") == "Tests MUST pass"
    assert _soften_caps("IMPORTANT: fix it") == "Important: fix it"


def test_разрешение_не_превращается_в_запрет():
    """«Можешь не трогать прод» → «Не трогать прод» меняло смысл на обратный."""
    from nativeprompt.rewrite import _strip_vague

    src = "Можешь не трогать прод, а почини @a.py"
    assert _strip_vague(src) == src
    # Вежливая обёртка без отрицания снимается как прежде.
    assert _strip_vague("Можешь починить @a.py").startswith("починить")


def test_восклицание_не_превращается_в_точку():
    """«Почини!!! баг» → «Почини. баг» меняло тип предложения посреди фразы."""
    from nativeprompt.rewrite import _soften_caps

    assert _soften_caps("Почини!!! баг") == "Почини! баг"


# ── шестой круг: гарды перевёрнуты с чёрного списка на белый ────────
def test_регистр_понижается_только_при_пустых_соседях():
    """Чёрный список «/._-» пробивался знаком `=` и кавычками."""
    from nativeprompt.rewrite import _soften_caps

    целые = [
        "https://api.example.com/v1?level=CRITICAL",
        "MODE=NEVER",
        'грепни по слову "MUST"',
        "MUST-README.md",
    ]
    for src in целые:
        assert _soften_caps(src) == src, src
    # «Tests MUST pass» больше НЕ понижается: английские слова-усилители сплошь
    # и рядом бывают техническим значением (уровень лога, значение конфига,
    # HTTP-метод), а по форме крик от значения не отличить. Понижаем их только
    # когда стоят заголовком — за ними двоеточие или восклицательный знак.
    assert _soften_caps("Tests MUST pass") == "Tests MUST pass"
    assert _soften_caps("IMPORTANT: fix it") == "Important: fix it"
    assert _soften_caps("ВАЖНО: рамки") == "Важно: рамки"


def test_разрешение_не_ломается_наречием():
    """Гард на одно соседнее слово не ловил «Можешь ПОКА не деплоить»."""
    from nativeprompt.rewrite import _strip_vague

    for src in ("Можешь пока не деплоить, сначала почини @a.py",
                "Можешь вообще не трогать тесты",
                "Можешь и не чинить это"):
        assert _strip_vague(src) == src, src
    # Обычная вежливость по-прежнему снимается, включая саму формулу «не мог бы».
    assert _strip_vague("Можешь починить @a.py").startswith("починить")
    assert _strip_vague("Не мог бы ты починить @a.py").startswith("починить")


def test_данные_в_кавычках_не_правятся():
    """`замени "x ; y" на "x; y"` превращалось в тождество."""
    from nativeprompt.explain import build_report

    out = build_report('ОБЯЗАТЕЛЬНО замени "x ; y" на "x; y" в @a.py', "claude-opus-5")["improved"]
    assert '"x ; y"' in out, out


def test_детектор_повторов_не_шире_ножа():
    """«Обязательно почини @a.py. Обязательно прогони тесты.» — повтор СЛОВА,
    который нож не убирает, а отчёт обещал «[-] Убрать повторы»."""
    assert "codex-lean" not in ids_for(
        "Обязательно почини баг в @a.py. Обязательно прогони тесты.", "gpt-5.6")
    assert "codex-lean" in ids_for("Сделай бэкап базы. Сделай бэкап базы.", "gpt-5.6")


def test_заглавная_после_переноса_строки():
    """Фикс мёртвой ветки из прошлого круга не был запинен."""
    from nativeprompt.rewrite import _soften_caps

    assert _soften_caps("# ЗАДАЧА\nОБЯЗАТЕЛЬНО почини") == "# ЗАДАЧА\nОбязательно почини"


# ── седьмой круг ────────────────────────────────────────────────────
def test_граница_слова_перед_глаголом_в_детекторе_цепочки():
    """Худшее за все круги: «дУМАЙ» находилось внутри «обДУМАЙ».

    «Обдумай пошагово» читалось детектором как то же самое указание модели,
    что и голое «думай пошагово» — тот же класс, что чинился на списке
    существительных пятью кругами раньше и не был проверен на глаголах.
    Правило (`codex-no-forced-cot`) теперь только предупреждает, поэтому текст
    в любом случае остаётся цел — проверяем только точность детектора.
    """
    from nativeprompt.explain import build_report

    from nativeprompt.analyze import _FORCED_COT

    for src in ("Обдумай пошагово", "Продумай пошагово задачу", "Rethink step by step"):
        assert not _FORCED_COT.search(src), "детектор: %r" % src
        out = build_report(src, "gpt-5.6")["improved"].split("\n")[0]
        assert src in out, "%r -> %r" % (src, out)
    # А настоящее указание модели по-прежнему детектится (просто больше не режется).
    assert _FORCED_COT.search("Напиши парсер, думай пошагово")
    assert "думай" in build_report("Напиши парсер, думай пошагово", "gpt-5.6")["improved"]


def test_данные_защищены_в_кавычках_кроме_апострофа():
    """Защита прямых кавычек была белым списком из одного вида: ёлочки и лапки
    портились так же, как прямые двойные, а в русском ёлочки — стандарт.

    Одинарные кавычки сюда намеренно НЕ входят — восьмой круг нашёл, что они
    съедают английский текст с апострофами («Don't», «it's»); см.
    `test_апостроф_не_маскирует_английский_текст` в разделе восьмого круга.
    """
    from nativeprompt.explain import build_report

    for кавычки in ('"a ; b"', "«a ; b»", "„a ; b“"):
        src = "ОБЯЗАТЕЛЬНО замени %s на что-то в @f.py" % кавычки
        out = build_report(src, "claude-opus-5")["improved"]
        assert кавычки in out, out


# ── восьмой круг: четыре дефекта в остающемся слое ───────────────────
def test_апостроф_не_маскирует_английский_текст():
    """В1. Одинарные кавычки в `CODE_SPAN` съедали английский текст.

    "Fix the bug in @src/auth.py. Don't guess, run the tests until it's
    green." — спан между "Don't" и "it's" маскировал «run the tests» целиком,
    и claude-verification срабатывало вслепую, хотя автор уже заказал прогон
    тестов. Дословный вызов из задания на фикс — им дефект и был найден.
    """
    from nativeprompt.analyze import analyze, mask_code

    src = "Don't guess, run the tests until it's green"
    assert mask_code(src) == src, mask_code(src)

    p = "Fix the bug in @src/auth.py. Don't guess, run the tests until it's green."
    got = {f["id"] for f in analyze(p, {"family": "claude", "generation": "opus-5"})}
    assert "claude-verification" not in got, got


def test_root_cause_срабатывает_на_русских_формах_но_не_на_prefix():
    """В2. `\\b` стоял только в конце группы `(почин|исправ|fix)\\b`.

    «fix» находился ВНУТРИ «prefix» (граница есть только после «fix», перед
    ним «e» — тоже буква, но регулярка всё равно засчитывала совпадение по
    границе в конце), а «почини»/«исправь» не находились вовсе — усечённый
    русский корень требовал границы сразу после себя, а следом всегда идёт
    падежное окончание.
    """
    from nativeprompt.analyze import _FIX_VERB, analyze

    assert not _FIX_VERB.search("prefix")

    got = {f["id"] for f in analyze("Почини баг", {"family": "claude", "generation": "opus-5"})}
    assert "claude-root-cause" in got, got


def test_verify_means_не_проваливается_внутрь_другого_слова():
    """В3. «тест» жил внутри «аттестации», «test» — внутри «latest».

    «Почини баг в модуле аттестации персонала» молча терял совет о проверке:
    упоминание «аттестации» ложно засчитывалось как упоминание тестов.
    """
    from nativeprompt.analyze import _VERIFY_MEANS, analyze

    assert not _VERIFY_MEANS.search("latest")

    got = {f["id"] for f in analyze("Почини баг в модуле аттестации персонала",
                                     {"family": "claude", "generation": "opus-5"})}
    assert "claude-verification" in got, got


def test_pushy_caps_детектор_согласован_с_ножом():
    """В4. Детектор капса не знал гарда соседей ножа и не ловил «Вы ОБЯЗАНЫ».

    `_soften_caps` молчит на `MODE=CRITICAL` и `https://ex.com/MUST-READ`
    (сосед не пуст — регистр там значим), а `_c_pushy_caps` этого гарда не
    знал и печатал находку там, где нож не тронет ни буквы. Заодно «Вы
    ОБЯЗАНЫ» и «ТЫ ДОЛЖЕН» вообще не детектились: проверка была
    регистрозависима, а формы «ОБЯЗАНЫ» не было в списке.
    """
    from nativeprompt.analyze import _c_pushy_caps

    t = {"family": "claude", "generation": "opus-5"}
    assert not _c_pushy_caps("MODE=CRITICAL", "mode=critical", t)
    assert not _c_pushy_caps("https://ex.com/MUST-READ", "https://ex.com/must-read", t)
    assert _c_pushy_caps("Вы ОБЯЗАНЫ", "вы обязаны", t)
    assert _c_pushy_caps("ТЫ ДОЛЖЕН", "ты должен", t)


def test_флагманский_пример_readme_совпадает_с_живым_выводом():
    """Доки расходились с кодом семь кругов подряд, и каждый раз — в одной из
    двух языковых половин. Пин восстановлен после перевода четырёх правил в
    предупреждения: у каждого README свой промпт, сверяем каждый со своим.
    """
    from nativeprompt.explain import build_report

    корень = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ru = ("Не мог бы ты пожалуйста ОБЯЗАТЕЛЬНО починить баг в логине, "
          "думай пошагово и обязательно перепроверь себя. Покажи только самое важное.")
    en = ("Could you please FIX the login bug, think step by step and "
          "double-check yourself. Only report the most important things.")

    пары = (
        ("README.ru.md", build_report(ru, "claude-opus-5")),
        ("README.ru.md", build_report(ru, "gpt-5.6")),
        ("README.md", build_report(en, "gpt-5.6")),
    )
    for файл, отчёт in пары:
        текст = io.open(os.path.join(корень, файл), encoding="utf-8").read()
        первая = отчёт["improved"].split("\n")[0].strip()
        assert первая in текст, "%s: разошлось с живым выводом: %r" % (файл, первая[:70])
        for f in отчёт["findings"]:
            if not f["always"]:
                assert f["title"][:34] in текст, (
                    "%s: заголовок находки %r в доке отсутствует" % (файл, f["title"][:50])
                )


# ── девятый круг ────────────────────────────────────────────────────
def test_обёртка_снимается_только_в_начале_всего_текста():
    """`outside_code` резала текст на сегменты, и якорь `^` шаблона обёртки
    совпадал с началом КАЖДОГО. Вежливый оборот после блока кода вырезался из
    середины, а слово склеивалось с бэктиком."""
    from nativeprompt.explain import build_report

    src = "Прочитай `README.md` можешь ли ты обновить раздел установки и прогнать тесты"
    out = build_report(src, "claude-opus-5")["improved"].split("\n")[0]
    assert "можешь ли ты обновить" in out, out
    assert "`README.md` можешь" in out, "склеено с кодом: %r" % out


def test_разрешение_переживает_вводный_оборот():
    """Гард отрицания смотрел до первой запятой, а вводный оборот вставляет
    запятую между «можешь» и «не» — разрешение становилось запретом."""
    from nativeprompt.explain import build_report

    for src in ("Можешь, в принципе, не деплоить сегодня — главное почини баг в @a.py",
                "Можешь, пожалуйста, не трогать прод, а почини @a.py",
                "Can you, for now, not deploy — just fix @a.py"):
        out = build_report(src, "claude-opus-5")["improved"].split("\n")[0]
        assert out.lower().startswith(("можешь", "can you")), "%r -> %r" % (src, out)


def test_приставочные_формы_проверки_засчитываются():
    """Левая граница у «тест» отсекла «протестируй» и «retest», и инструмент
    требовал проверку там, где автор её уже заказал."""
    assert "claude-verification" not in ids("Почини баг в @src/pay.py и протестируй изменения")
    assert "claude-verification" not in ids_for("Fix @src/pay.py and retest everything",
                                                "claude-opus-5")
    # А ложные срабатывания из прошлого круга не вернулись.
    assert "claude-verification" in ids("Почини баг в модуле аттестации персонала")


# ── десятый круг ────────────────────────────────────────────────────
def test_снятие_обёртки_не_ломает_команду_и_путь():
    """Заглавная после снятия обёртки подменяла букву в регистрозависимом
    токене: «Можешь npm ci» → «Npm ci», «Можешь src/utils.py» → «Src/utils.py»,
    "Can you git push" → "Git push". Тот же класс, что «.env почини» → «Env
    почини» из таблицы CLAIMS, вернувшийся через другую дверь.
    """
    from nativeprompt.explain import build_report

    случаи = [
        ("Можешь npm ci и потом почини баг в @a.py", "npm ci"),
        ("Можешь src/utils.py открыть и починить там баг", "src/utils.py"),
        ("Can you git push after fixing the bug in @a.py", "git push"),
        ("Можешь ли ты python3 -m pytest прогнать после правки @a.py", "python3 -m pytest"),
    ]
    for src, токен in случаи:
        out = build_report(src, "claude-opus-5")["improved"].split("\n")[0]
        assert токен in out, "%r -> %r" % (src, out)


def test_двойное_восклицание_в_коде_не_схлопывается():
    """`!!` — оператор, и его удаление переворачивает смысл: `!!user.flag` в JS
    становилось отрицанием, `user!!.name` в Kotlin ломалось, `xs !! 3` в
    Haskell уничтожалось. Схлопываем только концевое восклицание."""
    from nativeprompt.explain import build_report

    for src, кусок in (
        ("Почини isAdmin в @auth.js: должно быть !!user.flag, и прогони тесты", "!!user.flag"),
        ("Почини NPE на user!!.name в @Profile.kt и прогони тесты", "user!!.name"),
        ("Почини выборку xs !! 3 в @Main.hs СРОЧНО и прогони тесты", "xs !! 3"),
    ):
        out = build_report(src, "claude-opus-5")["improved"].split("\n")[0]
        assert кусок in out, "%r -> %r" % (src, out)
    # А крик по-прежнему снимается.
    assert "Почини!" in build_report("Почини!!! баг в @a.py", "claude-opus-5")["improved"]


def test_техническое_значение_капсом_не_понижается():
    """`logger.setLevel("CRITICAL")` ломается от понижения регистра, а по форме
    крик от значения не отличить — значит не трогаем. Английские усилители
    понижаются только заголовком: за ними двоеточие или восклицательный знак."""
    from nativeprompt.explain import build_report

    for src, токен in (
        ("Выставь уровень логирования CRITICAL в @settings.py и прогони тесты", "CRITICAL"),
        ("Обнови конфиг: level = IMPORTANT в @a.py и прогони тесты", "IMPORTANT"),
        ("Метод ALWAYS в @api.py оставь как есть, почини соседний", "ALWAYS"),
    ):
        out = build_report(src, "claude-opus-5")["improved"].split("\n")[0]
        assert токен in out, "%r -> %r" % (src, out)
    # Заголовком — понижается, и русские усилители тоже.
    assert "Important:" in build_report("IMPORTANT: fix @a.py", "claude-opus-5")["improved"]
    assert "Обязательно" in build_report("ОБЯЗАТЕЛЬНО почини @a.py", "claude-opus-5")["improved"]


def test_приставки_проверки_покрыты_целиком():
    """Хвост прошлого круга: по- и за- не попали в список приставок."""
    for глагол in ("протестируй", "потестируй", "затестируй", "перетестируй", "оттестируй"):
        assert "claude-verification" not in ids("Почини баг в @src/pay.py и %s изменения" % глагол), глагол
    assert "claude-verification" in ids("Почини баг в модуле аттестации персонала")


# ── одиннадцатый круг ───────────────────────────────────────────────
def test_капс_внутри_блока_кода_не_понижается():
    """Инвариант сравнивает слова без регистра и потому слеп к этой порче:
    литерал чужой программы менялся молча, а тесты оставались зелёными."""
    from nativeprompt.explain import build_report

    src = "ОБЯЗАТЕЛЬНО поправь:\n```python\n# ВАЖНО: не трогать\nMODE = 'CRITICAL'\n```\nи прогони тесты"
    out = build_report(src, "claude-opus-5")["improved"]
    assert "# ВАЖНО: не трогать" in out, out
    assert "'CRITICAL'" in out, out
    # А снаружи блока крик по-прежнему снимается.
    assert out.lstrip().startswith("Обязательно"), out


def test_детектор_крика_не_шире_ножа():
    """`!!` — оператор, нож его не трогает; значит и находки быть не должно.
    Обещать правку, которой не будет, — то же нарушение, что и порча текста."""
    for src in ("Почини isAdmin в @auth.js: должно быть !!user.flag, и прогони тесты",
                "Замени return user!! на элвис-оператор в @P.kt и прогони тесты"):
        assert "claude-dial-caps" not in ids(src), src
    # А настоящий крик ловится.
    assert "claude-dial-caps" in ids("Почини!!! баг в @a.py и прогони тесты")


def test_перенос_строки_не_делает_из_значения_заголовок():
    """`\\s*` в проверке «за словом двоеточие» перешагивал перевод строки, и
    `!important` из CSS на следующей строке понижал техническое значение."""
    from nativeprompt.explain import build_report

    src = ("Выставь уровень логирования CRITICAL\n"
           "!important в стилях не используй, почини @style.css и прогони тесты")
    out = build_report(src, "claude-opus-5")["improved"]
    assert "CRITICAL" in out, out
    # Заголовком на той же строке — по-прежнему понижается.
    assert "Important:" in build_report("IMPORTANT: fix @a.py", "claude-opus-5")["improved"]


def test_гард_соседей_держит_русский_капс_в_пути_и_ссылке():
    """Инвариант сравнивает слова без регистра и эту порчу пропускал.

    После сужения `CAPS_WORD` (англ. слово — только перед `:` или `!`)
    `MODE=CRITICAL` и `MUST-README.md` вообще перестали быть кандидатами, и
    гард соседей остался отвечать ровно за русский КАПС в регистрозначимых
    позициях. Снятие гарда 607 тестов не замечали.
    """
    for src in ("открой @docs/ВАЖНО.md",
                "см. https://wiki.local/СРОЧНО и почини",
                "выстави ПРИОРИТЕТ=СРОЧНО",
                "Слово-ВАЖНО-в-имени.txt"):
        assert _soften_caps(src) == src, src
    # А тот же КАПС отдельным словом по-прежнему понижается.
    assert _soften_caps("ВАЖНО почини") == "Важно почини"


def test_промпт_из_одних_пробелов_не_доходит_до_отчёта(monkeypatch):
    """Аргумент из пробелов truthy — и CLI печатал «улучшенный промпт»,
    состоящий из одной нашей добавки. Из stdin то же самое отсеивалось.

    stdin подменяем терминалом: иначе `_read_prompt` пойдёт читать поток,
    а под pytest чтение stdin запрещено — тест упал бы не по делу.
    """
    import io as _io
    from nativeprompt.__main__ import main

    class _Терминал(_io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr("sys.stdin", _Терминал())
    assert main(["improve", "   \t  ", "--model", "claude-opus-5"]) == 2
    assert main(["improve", "", "--model", "claude-opus-5"]) == 2


def test_прямые_кавычки_защищают_данные():
    """Мутация круга 18: убрать маскирование прямых кавычек — 843 теста зелёные.

    То есть защита цитируемых данных не проверялась вовсе, хотя ради неё
    кавычки в `CODE_SPAN` и заводились: `замени "ВАЖНО: не трогать" на …` —
    это инструкция ПРО текст, а не крик, и трогать его нельзя.
    """
    from nativeprompt.explain import build_report

    r = build_report('Замени в @a.py строку "ВАЖНО: не трогать" на "важно" и прогони тесты',
                     "claude-opus-5")
    assert '"ВАЖНО: не трогать"' in r["improved"], r["improved"]
    assert "claude-dial-caps" not in {f["id"] for f in r["findings"]}
    # И детектор не выдумывает находку по тексту внутри кавычек.
    r2 = build_report('Выведи сообщение "перепроверь себя" в @a.py и прогони тесты',
                      "claude-opus-5")
    assert "opus5-remove-verification" not in {f["id"] for f in r2["findings"]}
