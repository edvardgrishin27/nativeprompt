"""Переписывание промпта.

Два выхода:
  1. improved  — детерминированная структурная правка (убрать лишнее, добавить
     недостающие секции ПЛЕЙСХОЛДЕРАМИ ‹…›; задачу за автора НЕ додумываем).
  2. metaprompt — собранная инструкция под модель, которую выполняет ВАШ же
     Claude/Codex для «умной» переписи (движок «разбор + мета-промпт»).
"""

import re

from . import catalog
#: Одно определение на весь пакет для того, что должно совпадать у детектора и
#: переписчика. Держать здесь свою копию нельзя: две регулярки под одним именем
#: уже расходились — `rewrite` знал про незакрытый блок кода, `analyze` нет;
#: `_soften_caps` знал про давящие слова, `_c_pushy_caps` нет.
from .analyze import CODE_SPAN as _CODE_SPAN, CAPS_WORD as _CAPS_WORD, has_safe_neighbors, task_shape

_PLACEHOLDER = "‹уточните: %s›"


# ── чистки (removals / softenings) ──────────────────────────────────
def outside_code(fn, text):
    """Применить чистку ко всему, КРОМЕ кода.

    Промпт часто несёт кусок кода как данные. Чистка формы не должна туда лезть:
    `print("ВАЖНО: не трогать")` превращался в `print("Важно: не трогать")` —
    инструмент молча правил строковый литерал чужой программы.
    """
    out, prev = [], 0
    for m in _CODE_SPAN.finditer(text):
        out.append(fn(text[prev : m.start()]))
        out.append(m.group(0))
        prev = m.end()
    out.append(fn(text[prev:]))
    return "".join(out)


def _soften_caps(text):
    """Снять КРИК, не тронув ни одного слова по существу.

    Правило вендора — про КАПС как форму давления, а не про сами слова. Значит
    единственная безопасная операция здесь — понизить регистр. Всё остальное уже
    пробовали, и всё остальное ломалось:

      удаление слова   «ВАЖНО: рамки» → «рамки»          (обезглавленный абзац)
      удаление MUST    «Tests MUST pass» → «Tests pass»   (требование стало фактом)
      подстановка      «ты MUST run» → «нужно run»        (русское слово в английский)
                       «ОБЯЗАТЕЛЬНО почини» → «нужно почини» (аграмматично)

    Понижение регистра не может сломать ни грамматику, ни смысл, ни язык — потому
    что не меняет ни одного слова. Это и есть «безопасно по построению».
    """
    # Крик схлопываем только там, где восклицание завершает слово: «Почини!!!
    # баг». Внутри кода `!!` — оператор, и его удаление переворачивает смысл:
    # `!!user.flag` в JS становилось отрицанием, `user!!.name` в Kotlin ломалось,
    # `xs !! 3` в Haskell уничтожалось. Гард тот же по духу, что у КАПСа:
    # трогаем, только когда слева слово, а справа не продолжение выражения.
    text = re.sub(r"(?<=\w)!{2,}(?=\s|$)", "!", text)

    def down(m):
        word = m.group(0)
        # Слово внутри ссылки, пути или составного имени НЕ трогаем: там регистр
        # значим. `https://EXAMPLE.com/MUST-READ` превращалось в `.../must-READ`,
        # а `MUST-README.md` — в `must-README.md`, то есть в битое имя файла на
        # системе с учётом регистра. «Регистр не может сломать смысл» верно ровно
        # до первого регистрозависимого токена.
        # Гард на соседей — `has_safe_neighbors` из `analyze`, ОДИН на нож и на
        # детектор (`_c_pushy_caps`). Раньше каждый носил свою копию, и детектор
        # печатал «[-] Убрать давящие КАПС» там, где нож правильно молчал.
        if not has_safe_neighbors(text, m.start(), m.end()):
            return word
        # В начале строки или предложения слово остаётся с заглавной («Важно:»),
        # в середине — целиком строчное, иначе выходит «Tests Must pass».
        # Перевод строки НЕ обрезаем: после `rstrip()` он исчезал, и ветка
        # «слово в начале строки» была недостижима — «# ЗАДАЧА\nОБЯЗАТЕЛЬНО»
        # давало строчное «обязательно» в начале новой строки.
        head = text[: m.start()].rstrip(" \t")
        starts = not head or head[-1] in ".!?:;" or text[: m.start()].endswith(("\n", "\n "))
        return (word[0] + word[1:].lower()) if starts else word.lower()

    return _CAPS_WORD.sub(down, text)


def _tidy(text):
    """Добавить точку в конце однострочного промпта, если её нет.

    Раньше здесь жила построчная чистка шва (`_tidy_lines`: пробел перед
    знаком препинания, «, .» → «.») и капитализация первой буквы — обе
    появились ради следов, которые оставляли вырезающие ножи. Ножей, режущих
    середину текста, больше нет: единственная оставшаяся правка, которая
    создаёт шов в НАЧАЛЕ текста, — снятие вежливой обёртки (`_strip_vague`), а
    она уже сама ставит заглавную. Осталась только точка, которой в промпте
    могло не быть с самого начала, без единой правки инструмента.

    У списка и заголовков точка — чужая пунктуация («1. Первый пункт.» не
    нужно), поэтому правим только текст без переводов строк.
    """
    if "\n" not in text and text and text[-1] not in ".!?:":
        text += "."
    return text


#: Вежливая обёртка в начале промпта.
_VAGUE_OPENER = re.compile(
    r"(?i)^\s*(?:пожалуйста,?\s*)?(?:не мог(?:ли)? бы (?:ты|вы)|мог бы ты|можешь ли ты|"
    r"можешь\b|could you\s+please|could you|can you|would you)[,:]?\s*"
)
#: Отрицание в ПЕРВОЙ ФРАЗЕ ПОСЛЕ обёртки. «Можешь не трогать прод» — разрешение,
#: и снятие «можешь» превращает его в запрет. Гард на одно соседнее слово этого не
#: ловил: «Можешь ПОКА не деплоить», «Можешь ВООБЩЕ не трогать» проходили мимо.
#: Смотреть на весь текст тоже нельзя — тогда под гард попадала сама формула
#: «НЕ мог бы ты», и вежливость переставала сниматься вовсе.
_NEGATION = re.compile(r"(?i)\b(?:не|ни|not|don'?t|do not|never)\b")


def _strip_vague(text):
    """Снять вежливую обёртку в начале — но не тогда, когда это разрешение.

    Шаблон обёртки один (`_VAGUE_OPENER`): своя копия здесь уже расходилась с
    гардом и гасила его.
    """
    начало = _VAGUE_OPENER.match(text)
    if начало:
        # До конца ПРЕДЛОЖЕНИЯ, а не до первой запятой: вводный оборот вставляет
        # запятую между «можешь» и «не» — «Можешь, в принципе, не деплоить»
        # проходило мимо гарда, и разрешение превращалось в запрет.
        первая_фраза = re.split(r"[.!?\n]", text[начало.end():], maxsplit=1)[0]
        if _NEGATION.search(первая_фраза):
            return text                      # разрешение, а не вежливая обёртка
    text2 = _VAGUE_OPENER.sub("", text, count=1)
    # если после снятия «не мог бы ты» осталось ведущее «пожалуйста» — тоже убрать
    text2 = re.sub(r"(?i)^\s*пожалуйста,?\s*", "", text2)
    # Заглавную НЕ ставим. Остаток после обёртки часто начинается с
    # регистрозависимого токена: «Можешь npm ci…» превращалось в «Npm ci»,
    # «Можешь src/utils.py открыть» — в «Src/utils.py», «Can you git push» — в
    # «Git push». Команда и путь ломаются, а косметическая заглавная не стоит
    # ничего. Тот же класс, что «.env почини» → «Env почини» из таблицы CLAIMS:
    # он вернулся через другую дверь, и дверь закрыта совсем.
    return text2


def rewrite(prompt, target, findings, shape=None):
    """Вернуть {improved, applied, additions_added}."""
    family = target.get("family")
    ids = {f["id"] for f in findings}
    if shape is None:
        shape = task_shape(prompt)

    core = prompt.strip()
    applied = []

    if "claude-explicit-action" in ids or "codex-explicit-action" in ids:
        # НЕ через outside_code: та режет текст на сегменты по код-спанам, и
        # якорь `^` совпадает с началом КАЖДОГО сегмента — «Прочитай `README.md`
        # можешь ли ты обновить…» теряло «можешь ли ты» из СЕРЕДИНЫ и склеивало
        # слово с бэктиком. Обёртка по определению стоит в начале всего текста,
        # поэтому применяется к нему целиком, а `^` в шаблоне и есть вся защита.
        new = _strip_vague(core)
        if new != core:
            core, _ = new, applied.append("claude-explicit-action" if "claude-explicit-action" in ids else "codex-explicit-action")
    if "claude-dial-caps" in ids or "codex-dial-scaffold" in ids:
        new = outside_code(_soften_caps, core)
        if new != core:
            core = new
            applied.append("claude-dial-caps" if "claude-dial-caps" in ids else "codex-dial-scaffold")
    # `codex-no-forced-cot`, `opus5-report-all`, `fable5-no-show-thinking` и
    # `codex-lean` намеренно НЕ применяются к тексту — как и `opus5-remove-
    # verification` раньше. Все четыре когда-то резали: цепочку рассуждений,
    # «только важное», просьбу показать рассуждение, дословные повторы. Восемь
    # кругов независимого ревью нашли в общей сложности больше двадцати разных
    # способов, которыми эти ножи молча портили смысл, данные или грамматику
    # («Обдумай пошагово» → «Об.», «покажи не только важное» → «покажи не
    # всё», «прогони тесты» между двумя шагами процедуры исчезало как
    # «повтор»). Отличить вежливый оборот или нытьё-повтор от части задания по
    # форме слов нельзя — открытая задача разбора языка, а не недоделанная
    # регулярка. Инструмент теперь только ПОКАЗЫВАЕТ находку, режет человек.

    if applied:  # прибираем шов только если что-то реально вырезали/смягчили
        core = _tidy(core)
    else:
        # Ничего не вырезали — значит и прибирать нечего. Раньше здесь всё равно
        # схлопывались двойные пробелы, причём в обход `outside_code` и построчной
        # защиты `_tidy`. На промпте с блоком Python отступы превращались в один
        # пробел, и человек получал СЛОМАННЫЙ код — на самом частом пути, когда ни
        # одно правило не сработало. Правило простое: не трогать текст, который не
        # правил.
        core = core.strip()

    # ── добавления (плейсхолдеры, не выдумываем содержание) ──────────
    additions = []  # (tag, label, content)
    def add(rule_id, tag, label, content):
        if rule_id in ids:
            additions.append((tag, label, content))
            applied.append(rule_id)

    add("claude-scope", "context",
        "Контекст",
        "‹назовите файл/путь через @ (напр. @src/...), сценарий и что значит «готово»›")
    add("claude-reference-files", "context", "Файлы",
        "‹сошлитесь на конкретные файлы через @, а не описанием›")
    add("claude-root-cause", "context", "Симптом",
        "‹что именно ломается, где искать (файл/модуль) и что значит «починено»; лечить причину, не симптом›")
    add("claude-verification", "verification", "Проверка",
        "‹тест/сборка/команда, которую нужно прогнать после правки, и чинить, пока не пройдёт›")
    add("claude-output-contract", "output_format", "Формат результата",
        "‹что должно получиться: структура, длина, ограничения›")
    add("codex-outcome-contract", "output_format", "Формат результата и критерий «готово»",
        "‹желаемый результат + как проверить, что задача выполнена (напр. `npm test` exit 0)›")
    add("codex-agents-md", "note", "Заметка",
        "постоянные правила проекта вынесите в AGENTS.md, а в промпте оставьте только эту задачу")

    # always-добавления
    if "opus5-concise" in ids:
        additions.append(("note", "Краткость", "Ответь кратко."))
        applied.append("opus5-concise")
    # политика «для каких форм задачи» живёт в rules/*.json (when_shapes) —
    # analyze уже отфильтровал, второй раз здесь не проверяем (один источник правды)
    if "codex-autonomy" in ids:
        additions.append(("note", "Автономность",
                           "Доведи задачу до конца; при неоднозначности действуй с разумными допущениями, не останавливайся на анализе."))
        applied.append("codex-autonomy")

    improved = _assemble(core, additions, family, ids)
    return {"improved": improved, "applied": applied, "additions": additions, "shape": shape}


def _assemble(core, additions, family, ids):
    use_xml = family == "claude" and "claude-xml" in ids
    if use_xml:
        blocks = ["<instructions>\n%s\n</instructions>" % core]
        for tag, _label, content in additions:
            blocks.append("<%s>\n%s\n</%s>" % (tag, content, tag))
        return "\n\n".join(blocks)
    if family == "openai":
        blocks = [core]
        for tag, label, content in additions:
            if tag == "note":
                blocks.append("(%s: %s)" % (label, content))
            else:
                blocks.append("## %s\n%s" % (label, content))
        return "\n\n".join(blocks)
    # claude без xml / прочее
    blocks = [core]
    for tag, label, content in additions:
        if tag == "note":
            blocks.append("(%s: %s)" % (label, content))
        else:
            blocks.append("%s: %s" % (label, content))
    return "\n\n".join(blocks)


# ── мета-промпт для «умной» переписи руками вашей же модели ───────────
def build_metaprompt(prompt, target, findings, harness_rec=None):
    family = target.get("family")
    data = catalog.load_family(family) if family else {}
    cli = data.get("display", family or "модель")
    label = target.get("model_id") or data.get("display", family or "текущая модель")

    rule_lines = []
    for f in findings:
        source = f.get("source", "")
        source_suffix = " Источник: %s" % source if source else ""
        rule_lines.append("- %s: %s%s" % (f["title"], f["why"], source_suffix))
    rules_block = "\n".join(rule_lines) if rule_lines else "- (существенных правок правила не требуют)"

    harness_block = ""
    if harness_rec:
        harness_source = harness_rec.get("source", "")
        harness_source_suffix = " Источник: %s" % harness_source if harness_source else ""
        harness_block = (
            "\nФорма задачи: %s. Рекомендуемый запуск в %s: %s — %s%s\n"
            % (
                harness_rec["shape"],
                harness_rec["cli"],
                harness_rec["command"],
                harness_rec["why"],
                harness_source_suffix,
            )
        )

    return (
        "Ты — редактор промптов для %s. Перепиши промпт из блока PROMPT под %s строго "
        "по официальным правилам ниже. НИЧЕГО не додумывай за автора: если данных не "
        "хватает — оставь явный плейсхолдер ‹…›, не выдумывай задачу.\n\n"
        "Правила %s:\n%s\n%s\n"
        "Верни РОВНО:\n"
        "1) Улучшенный промпт (готов к вставке).\n"
        "2) 3–5 строк «что изменил и почему», каждая — со ссылкой на правило.\n\n"
        "PROMPT:\n<<<\n%s\n>>>"
        % (cli, label, cli, rules_block, harness_block, prompt.strip())
    )
