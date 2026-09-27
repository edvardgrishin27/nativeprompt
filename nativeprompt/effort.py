"""Рекомендация уровня усилий: какой effort ставить под форму задачи и модель.

Claude Code: /effort low…max и ultracode.
Codex:       model_reasoning_effort в ~/.codex/config.toml (у /plan — свой ключ).
Данные — из блока "effort" в rules/<family>.json: уровни и дефолт каждой
модели, совет под каждую форму задачи, у каждого совета ссылка на вендора.

Уровень — настройка запуска, а не слова в промпте. Поэтому ни в улучшенный
промпт, ни в мета-промпт он не попадает: вендоры просят управлять глубиной
рассуждения уровнем, а не фразами вроде «думай тщательнее».

Советы у двух вендоров устроены по-разному, и это не упрощение, а их позиция.
Anthropic пишет, что дефолт подходит для большинства задач по коду, и меняет
уровень только под другой баланс расхода и интеллекта. OpenAI на странице
моделей Codex называет уровень, с которого начинать каждую модель, и советует
поднимать его, когда задаче нужно больше планирования, анализа или проверки.
Поэтому у Claude почти все формы задачи ведут к дефолту модели, а у Codex —
к своему уровню.
"""

from . import catalog

#: Лестница уровней от слабого к сильному. Нужна для одного: когда модель не
#: знает советованного уровня, взять самый высокий из её уровней не выше совета.
#: Так поступает сам Claude Code: `xhigh` на Opus 4.6 работает как `high`.
_LADDER = ("none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra", "ultracode")

#: Слово в данных, которое значит «дефолт этой модели», а не конкретный уровень.
_DEFAULT = "default"


def _step(level):
    return _LADDER.index(level) if level in _LADDER else -1


def fit_level(wanted, levels):
    """Самый высокий уровень из `levels`, не выше `wanted`.

    Нет такого — самый низкий из доступных: совет «low» модели, у которой low
    нет, честнее превратить в её нижнюю ступень, чем промолчать. Пустой список
    значит, что effort у модели нет вовсе, и ответ тогда None.
    """
    if not levels:
        return None
    if wanted in levels:
        return wanted
    ниже = [l for l in levels if _step(l) <= _step(wanted)]
    if ниже:
        return max(ниже, key=_step)
    return min(levels, key=_step)


def recommend_effort(target, shape):
    """Вернуть рекомендацию уровня усилий для модели и формы задачи.

    None — у семейства нет блока "effort" (Gemini, Grok, Kimi, Qwen): данных о
    том, как вендор советует выбирать уровень, у инструмента нет, и выдумывать
    их он не станет.
    """
    family = target.get("family")
    if not family:
        return None
    data = catalog.load_family(family)
    eff = data.get("effort")
    if not eff:
        return None
    by_shape = eff["by_shape"]
    # Неизвестная форма идёт в `normal`, как и у харнесса: это корзина для
    # всего, в чём форма не определилась, и совет там — дефолт модели.
    advice = by_shape.get(shape) or by_shape["normal"]
    gen = target.get("generation")
    model = eff["models"].get(gen) if gen else None
    label = (data.get("generations", {}).get(gen) or {}).get("label") if gen else None

    rec = {
        "cli": eff["cli"],
        "shape": shape,
        "model": label or target.get("model_id") or data.get("display", family),
        "why": advice["why"],
        "source": advice["source"],
        "supported": True,
        "level": None,
        "is_default": False,
        # У Claude Code это настоящий дефолт модели, у Codex — уровень, с которого
        # вендор советует начинать: сам дефолт по моделям он не публикует.
        "default_label": eff.get("default_label", "это дефолт модели"),
        "command": "",
        "model_note": None,
        "raise_when": eff.get("raise_when"),
        "caution": advice.get("caution"),
    }

    if model is not None and model.get("levels") == []:
        # Модель известна, и у вендора прямо сказано, что effort у неё нет.
        rec.update(supported=False, why=eff["unsupported"]["text"],
                   source=eff["unsupported"]["source"], raise_when=None, caution=None)
        return rec

    # `levels: None` — вендор не публикует список уровней этой модели (так у
    # GPT-5.6 в Codex). Тогда уровень не подгоняем: подгонять не к чему.
    levels = model.get("levels") if model is not None else None
    default = model.get("default") if model is not None else None
    if model is not None and model.get("note"):
        rec["model_note"] = {"text": model["note"], "source": model["note_source"]}

    wanted = advice["level"]
    if wanted == _DEFAULT:
        if default is None:
            # Поколение не определилось («opus», незнакомый id). Дефолт у моделей
            # разный, угадывать его нельзя; конкретный совет вроде low — можно.
            rec["unknown_default"] = eff["unknown_default"]
            rec["command"] = eff["set"]["command"].format(level="‹уровень›")
            return rec
        level = default
    elif levels is None:
        # Какие уровни у модели есть, неизвестно: советуем как есть и прямо
        # говорим, что делать, если такого уровня у неё не окажется.
        level = wanted
        rec["levels_unknown"] = eff["levels_unknown"].format(level=wanted)
    else:
        # У составного уровня своя граница подмены. Ultracode — это xhigh плюс
        # воркфлоу, и без него Claude Code берёт уровень не выше xhigh, а не max,
        # хотя max на лестнице стоит выше.
        искомое = wanted if wanted in levels else eff.get("fallback_as", {}).get(wanted, wanted)
        level = fit_level(искомое, levels)
        if level != wanted and advice.get("fallback_why"):
            # Модель не умеет советованный уровень: объясняем подмену. Оговорка
            # про сам уровень (лимит ultracode, где включить Ultra) к подменённому
            # уровню не относится и только сбила бы с толку.
            rec["why"] = advice["fallback_why"]
            rec["source"] = advice.get("fallback_source", rec["source"])
            rec["caution"] = None
    # `floor` — совет «не ниже стартового уровня модели». У Codex слабой модели
    # вендор сразу советует уровень выше (Luna начинает с high), и опускать её
    # под планирование до medium значило бы спорить с самим вендором.
    if advice.get("floor") and default is not None and _step(level) < _step(default):
        level = default
    rec["is_default"] = default is not None and level == default

    rec["level"] = level
    шаблон = (advice.get("commands") or {}).get(level) or eff["set"]["command"]
    rec["command"] = шаблон.format(level=level)
    return rec
