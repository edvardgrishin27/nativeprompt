"""Детерминированный разбор промпта: какие правила семейства «срабатывают»
и какая у задачи форма (для рекомендации харнесса).

Ноль обращений к модели — только регэкспы/эвристики (RU+EN). Каждый детектор
привязан к правилу из rules/<family>.json по имени в поле "check".
"""

import re

from . import catalog

_CODING_VERB = re.compile(
    r"(напиш|добав|почин|исправ|сдела|реализ|перепиш|отрефактор|рефактор|создай|"
    r"удали|обнови|напис|implement|fix\b|add\b|write\b|refactor|create|build\b|"
    r"update\b|remove\b|migrat|тест|debug|отлад)",
    re.I,
)
_PATH = re.compile(
    r"@|/|\b\w+\.(py|ts|tsx|js|jsx|go|rs|java|rb|php|json|md|html|css|scss|sql|yml|yaml|toml)\b"
    r"|\bsrc\b|\bкаталог|\bпапк|\bмодул",
    re.I,
)
_VERIFY_MEANS = re.compile(
    r"(тест|test|сборк|build|pytest|jest|npm |lint|прогони|run |скрин|screenshot|"
    r"exit code|assert|провер\w* (что|сборк|прошл)|passes|компилир)",
    re.I,
)


def _coding_task(low):
    return bool(_CODING_VERB.search(low))


# ── детекторы (check-имена из шпаргалок) ─────────────────────────────
def _c_always(p, low, t):
    return True


def _c_missing_context(p, low, t):
    return _coding_task(low) and not _PATH.search(p)


def _c_missing_verification(p, low, t):
    return _coding_task(low) and not _VERIFY_MEANS.search(low)


def _c_describe_location(p, low, t):
    return bool(
        re.search(r"(файл[,]?\s+(где|в котором|котор)|там,?\s+где|где-то в|"
                  r"in the file (that|where)|the file that)", low)
    ) and "@" not in p


def _c_fix_symptom(p, low, t):
    fix = re.search(r"(почин|исправ|fix)\b", low) and re.search(
        r"(баг|ошибк|не работает|падает|failing|broken|\bbug\b|crash|сломал)", low
    )
    detail = re.search(r"(причин|root cause|симптом|потому что|because|@|/|src)", low)
    return bool(fix) and not detail


def _c_missing_output_contract(p, low, t):
    produce = re.search(
        r"(напиш|сдела|сгенер|состав|выведи|подготов|summar|\blist\b|generate|"
        r"\bwrite\b|отчёт|report|объясн|explain)",
        low,
    )
    fmt = re.search(
        r"(формат|в виде|верни|возврат|структур|json|таблиц|список|markdown|bullet|"
        r"ответь\s|\bformat\b|\boutput\b|критери\w* готов|что считается|counts as done|"
        r"exit 0|ok или fail|ok/fail)",
        low,
    )
    return bool(produce) and not fmt


def _c_vague_ask(p, low, t):
    return bool(
        re.search(
            r"(не мог(ли)? бы (ты|вы)|мог бы ты|можешь ли ты|\bможешь\b|could you|"
            r"can you|would you|пожалуйста,?\s+(предлож|подумай|посмотр)|давай(те)? попроб)",
            low,
        )
    )


def _c_pushy_caps(p, low, t):
    if re.search(r"!!!", p):
        return True
    if re.search(r"\b(КРИТИЧНО|ОБЯЗАТЕЛЬНО|ВАЖНО|СРОЧНО|CRITICAL|MUST|ALWAYS|NEVER|IMPORTANT)\b", p):
        return True
    if re.search(r"\b(ты|вы|you)\s+(ДОЛЖЕН|ДОЛЖНЫ|ОБЯЗАН|MUST)\b", p):
        return True
    return False


def _c_missing_xml(p, low, t):
    if t.get("family") != "claude":
        return False
    multi = len(p) > 500 or bool(
        re.search(r"(пример:|example:|данные:|контекст:|вот текст|```|<<<|инструкци\w*:)", low)
    )
    has_xml = re.search(r"<[a-zA-Z_][a-zA-Z0-9_]*>", p)
    return multi and not has_xml


def _c_verification_demand(p, low, t):
    return bool(
        re.search(
            r"(перепровер|убедись,?\s+что|дважды провер|double.?check|re-?verify|"
            r"verify your|проверь себя|make sure you|тщательно проверь)",
            low,
        )
    )


def _c_report_only_high(p, low, t):
    return bool(
        re.search(
            r"(только\s+(важн|критич|серьёзн|high|severe|major|значим)|report only|"
            r"только самое важное|only (high|critical|major|the most))",
            low,
        )
    )


def _c_forced_cot(p, low, t):
    return bool(
        re.search(
            r"(думай пошагово|шаг за шагом|по шагам|пошагово|think step by step|"
            r"step[- ]by[- ]step|let'?s think|chain of thought|рассуждай вслух|"
            r"распиши (свои )?рассуждени|покажи ход мыслей)",
            low,
        )
    )


def _c_repetition(p, low, t):
    sents = [s.strip() for s in re.split(r"[.!?\n]+", low) if len(s.strip()) > 12]
    seen = {}
    for s in sents:
        seen[s] = seen.get(s, 0) + 1
        if seen[s] >= 2:
            return True
    for key in ("обязательно", "сначала спроси", "не забудь", "напоминаю"):
        if low.count(key) >= 2:
            return True
    return False


def _c_contradiction_hint(p, low, t):
    pairs = [
        ("кратко", "подробно"),
        ("кратко", "детальн"),
        ("коротко", "развернут"),
        ("markdown", "без форматирован"),
        ("без форматирован", "в формате"),
        ("быстро", "тщательно"),
        ("brief", "detailed"),
    ]
    return any(a in low and b in low for a, b in pairs)


def _c_needs_agents_md(p, low, t):
    if t.get("family") != "openai":
        return False
    return bool(
        re.search(
            r"(всегда|каждый раз|во всех задачах|в целом по проекту|стиль кода|"
            r"code style|always use|every time|по всему проекту)",
            low,
        )
    )


_CHECKS = {
    "always": _c_always,
    "missing_context": _c_missing_context,
    "missing_verification": _c_missing_verification,
    "describe_location": _c_describe_location,
    "fix_symptom": _c_fix_symptom,
    "missing_output_contract": _c_missing_output_contract,
    "vague_ask": _c_vague_ask,
    "pushy_caps": _c_pushy_caps,
    "missing_xml": _c_missing_xml,
    "verification_demand": _c_verification_demand,
    "report_only_high": _c_report_only_high,
    "forced_cot": _c_forced_cot,
    "repetition": _c_repetition,
    "contradiction_hint": _c_contradiction_hint,
    "needs_agents_md": _c_needs_agents_md,
}


def analyze(prompt, target):
    """Вернуть список сработавших правил (findings) для данной модели.

    target: {family, generation}. Правила scope='family' проверяются всегда;
    scope=<generation-id> — только если target.generation совпадает.
    Правила с action='add'/check='always' не включаем в findings как «проблему»,
    их подхватывает rewrite/harness (кроме явных — они попадают в 'additions').
    """
    family = target.get("family")
    if not family:
        return []
    data = catalog.load_family(family)
    low = prompt.lower()
    shape = None
    findings = []
    for rule in data.get("rules", []):
        scope = rule.get("scope", "family")
        if scope != "family" and scope != target.get("generation"):
            continue
        allowed_shapes = rule.get("when_shapes")
        if allowed_shapes:
            if shape is None:
                shape = task_shape(prompt)
            if shape not in allowed_shapes:
                continue
        check = rule.get("check", "always")
        fn = _CHECKS.get(check)
        if fn is None:
            continue
        if check == "always":
            # 'always'-правила — это добавления по умолчанию для поколения,
            # их показываем как рекомендации, но помечаем отдельно
            findings.append(_as_finding(rule, always=True))
            continue
        if fn(prompt, low, target):
            findings.append(_as_finding(rule, always=False))
    return findings


def _as_finding(rule, always):
    return {
        "id": rule["id"],
        "title": rule["title"],
        "action": rule.get("action", "warn"),
        "why": rule.get("why", ""),
        "source": rule.get("source", ""),
        "check": rule.get("check", ""),
        "scope": rule.get("scope", "family"),
        "always": always,
    }


# ── форма задачи (для харнесса) ──────────────────────────────────────
_SHAPE_WORKFLOW = re.compile(
    r"(по всем файлам|во всех файлах|(все|всех|каждый|каждого)\s+файл\w*|по всему проекту|"
    r"across (all|every)|every file|codebase[- ]wide|весь проект целиком|тысяч\w* файл|"
    r"аудит безопасност|security audit|миграци\w* тысяч|(entire|whole) codebase)",
    re.I,
)
_SHAPE_LOOP = re.compile(
    r"(кажд(ый|ое|ую)\s+(день|утро|ночь|неделю|час)|ежедневн|ежечас|nightly|"
    r"по расписани|periodic|every (night|morning|day|hour|week)|раз в день|раз в час)",
    re.I,
)
_SHAPE_GOAL = re.compile(
    r"((пока|until|до тех пор)\b[^.\n]{0,60}"
    r"(пройд|прошл|проход|зелён|готов|заверш|compil|pass|hold|green|empty|исчез|пуст|clean|чист)"
    r"|до зелён|all tests pass|acceptance criteria|критери\w* приёмк|до готовн|backlog|"
    r"очередь задач|доведи до|доведи задачу)",
    re.I,
)
_SHAPE_PLANNING = re.compile(
    r"(как лучше|какой подход|с чего начать|спроектир|design (a|the)|архитектур|"
    r"architecture|отрефактор|\brefactor\b|не уверен|несколько файлов|multiple files|"
    r"how (should|do) (i|we)|продумай план|состав\w* план|нужно продумать)",
    re.I,
)
_SHAPE_TRIVIAL = re.compile(
    r"(переименуй|опечат|\btypo\b|\brename\b|добавь лог|add a log|подправь|"
    r"поправь мелк|один символ|измени строк)",
    re.I,
)


def task_shape(prompt):
    """Классифицировать задачу: workflow | loop | goal | planning | trivial | normal."""
    low = prompt.lower()
    if _SHAPE_WORKFLOW.search(low):
        return "workflow"
    if _SHAPE_LOOP.search(low):
        return "loop"
    if _SHAPE_GOAL.search(low):
        return "goal"
    if _SHAPE_PLANNING.search(low):
        return "planning"
    if len(prompt.strip()) <= 120 and _SHAPE_TRIVIAL.search(low):
        return "trivial"
    if len(prompt.strip()) <= 90 and _coding_task(low):
        return "trivial"
    return "normal"
