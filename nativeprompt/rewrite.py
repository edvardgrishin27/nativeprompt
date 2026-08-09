"""Переписывание промпта.

Два выхода:
  1. improved  — детерминированная структурная правка (убрать лишнее, добавить
     недостающие секции ПЛЕЙСХОЛДЕРАМИ ‹…›; задачу за автора НЕ додумываем).
  2. metaprompt — собранная инструкция под модель, которую выполняет ВАШ же
     Claude/Codex для «умной» переписи (движок «разбор + мета-промпт»).
"""

import re

from . import catalog
from .analyze import task_shape

_PLACEHOLDER = "‹уточните: %s›"


# ── чистки (removals / softenings) ──────────────────────────────────
def _soften_caps(text):
    """Снять крик, не тронув смысл и структуру.

    Раньше слова-усилители вырезались целиком. Но «ВАЖНО» в начале строки — это чаще
    заголовок раздела, а не крик: удаление обезглавливало абзац, и человек получал
    текст, из которого пропал кусок. Правило было про КАПС как форму давления, поэтому
    правильная реакция — понизить регистр, а не удалить слово.
    """
    text = re.sub(r"!!!+", ".", text)
    text = re.sub(r"\b(ты|вы|you)\s+(ДОЛЖЕН|ДОЛЖНЫ|ОБЯЗАН|MUST)\b", "нужно", text)
    text = re.sub(
        r"\b(КРИТИЧНО|ВАЖНО|СРОЧНО|CRITICAL|IMPORTANT|ALWAYS|NEVER)\b",
        lambda m: m.group(1)[0] + m.group(1)[1:].lower(),
        text,
    )
    text = re.sub(r"\bОБЯЗАТЕЛЬНО\b", "нужно", text)
    text = re.sub(r"\bMUST\b", "", text)
    return text


def _tidy(text):
    """Прибрать шов после вырезаний, НЕ трогая разметку исходника.

    Две ошибки, которые здесь стояли и портили живые промпты.

    Первая: `re.sub(r"\\s+", " ", text)` схлопывал переводы строк вместе с пробелами.
    Промпт с заголовками и нумерованным списком возвращался одним абзацем — нумерация
    и переносы исчезали. Теперь чистка идёт ПОСТРОЧНО, разметка переживает правку.

    Вторая: `([а-яa-z0-9])\\s+([А-ЯA-Z][а-яa-z])` → `\\1. \\2` — попытка развести
    слипшиеся после вырезания предложения. Отличить склейку от имени собственного
    так нельзя: «планировщик Windows» превращался в «планировщик. Windows», «в России»
    в «в. России». Эвристика удалена целиком — тихо ломать текст хуже, чем оставить
    шов. Незакрытую строку добиваем точкой в конце, этого достаточно.
    """
    lines = text.split("\n")
    out = []
    for line in lines:
        s = re.sub(r"[ \t]+([,.;:!?])", r"\1", line)        # пробел перед знаком
        s = re.sub(r"[ \t]{2,}", " ", s)
        s = re.sub(r"(?i)(^|[.!?]\s*)(и|а|но)\s+", r"\1", s)  # висящий союз
        s = re.sub(r",\s*([.!?])", r"\1", s)                  # ", ." → "."
        out.append(s.rstrip())
    text = "\n".join(out).strip("\n")

    # Заглавная в начале и точка в конце — только у сплошного текста. У списка и
    # заголовков это чужая пунктуация: точка после «1. Первый пункт» не нужна.
    if "\n" not in text:
        text = text.strip()
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        if text and text[-1] not in ".!?:":
            text += "."
    return text


def _strip_cot(text):
    return re.sub(
        r"(?i)[,.;]?\s*(и\s+)?(обязательно\s+)?(думай пошагово|шаг за шагом|по шагам|пошагово|"
        r"think step by step|step[- ]by[- ]step|let'?s think(?: step by step)?|"
        r"рассуждай вслух|покажи ход мыслей|распиши (свои )?рассуждени\w*)[.,]?",
        "",
        text,
    )


def _strip_verification_demand(text):
    return re.sub(
        r"(?i)[,.;]?\s*(и\s+)?(обязательно\s+)?(перепроверь( себя| ещё раз)?|"
        r"убедись,?\s+что[^.,\n]*|дважды проверь[^.,\n]*|double.?check[^.,\n]*|"
        r"re-?verify[^.,\n]*|проверь себя|make sure you[^.,\n]*)[.,]?",
        "",
        text,
    )


def _strip_vague(text):
    text2 = re.sub(
        r"(?i)^\s*(пожалуйста,?\s*)?(не мог(ли)? бы (ты|вы)|мог бы ты|можешь ли ты|"
        r"можешь\b|could you\s+please|could you|can you|would you)[,:]?\s*",
        "",
        text,
    )
    # если после снятия «не мог бы ты» осталось ведущее «пожалуйста» — тоже убрать
    text2 = re.sub(r"(?i)^\s*пожалуйста,?\s*", "", text2)
    if text2 and text2 != text:
        text2 = text2[0].upper() + text2[1:]
    return text2


def _report_all(text):
    return re.sub(
        r"(?i)только\s+(самое\s+)?(важн\w*|критич\w*|значим\w*|серьёзн\w*|high|severe|major)",
        "всё (значимое отфильтруешь отдельным проходом)",
        text,
    )


def _dedupe_sentences(text):
    """Убрать дословные повторы, сохранив разбивку на строки.

    Раньше результат склеивался через `" ".join(...)` — то есть дедуп заодно
    уничтожал переводы строк, даже когда ни одного повтора не нашлось.
    """
    seen = set()
    out_lines = []
    for line in text.split("\n"):
        parts = re.split(r"(?<=[.!?])\s+", line)
        kept = []
        for p in parts:
            key = p.strip().lower()
            if len(key) > 12:
                if key in seen:
                    continue
                seen.add(key)
            kept.append(p)
        out_lines.append(" ".join(kept))
    return "\n".join(out_lines)


def rewrite(prompt, target, findings, shape=None):
    """Вернуть {improved, applied, additions_added}."""
    family = target.get("family")
    ids = {f["id"] for f in findings}
    if shape is None:
        shape = task_shape(prompt)

    core = prompt.strip()
    applied = []

    if "claude-explicit-action" in ids or "codex-explicit-action" in ids:
        new = _strip_vague(core)
        if new != core:
            core, _ = new, applied.append("claude-explicit-action" if "claude-explicit-action" in ids else "codex-explicit-action")
    if "claude-dial-caps" in ids or "codex-dial-scaffold" in ids:
        new = _soften_caps(core)
        if new != core:
            core = new
            applied.append("claude-dial-caps" if "claude-dial-caps" in ids else "codex-dial-scaffold")
    if "codex-no-forced-cot" in ids:
        new = _strip_cot(core)
        if new != core:
            core, _ = new, applied.append("codex-no-forced-cot")
    if "opus5-remove-verification" in ids:
        new = _strip_verification_demand(core)
        if new != core:
            core, _ = new, applied.append("opus5-remove-verification")
    if "opus5-report-all" in ids:
        new = _report_all(core)
        if new != core:
            core, _ = new, applied.append("opus5-report-all")
    if "codex-lean" in ids:
        new = _dedupe_sentences(core)
        if new != core:
            core, _ = new, applied.append("codex-lean")

    if applied:  # прибираем шов только если что-то реально вырезали/смягчили
        core = _tidy(core)
    else:
        core = re.sub(r"[ \t]{2,}", " ", core).strip()

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
