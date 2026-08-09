"""Рекомендация «как запускать» под форму задачи и текущий CLI.

Claude Code: просто напиши / plan mode / /goal / /loop / dynamic workflow.
Codex:       просто напиши / /plan / /goal / делегировать (parallel).
Данные — из блока "harness" в rules/<family>.json (значит, тоже самообновляемы).
"""

from . import catalog
from .analyze import task_shape

#: Ответ по умолчанию, когда форму задачи по тексту определить не удалось.
#: Живёт в коде, а не в данных: иначе каждое новое семейство молча наследует
#: чужую ветку и начинает уверенно советовать не то.
_UNKNOWN_SHAPE = {
    "command": "начните обычным запуском; при первой же неясности — режим плана",
    "title": "Форма задачи по тексту не определилась",
    "why": ("Задача не выглядит ни мелкой правкой, ни явным планированием, ни работой "
            "до измеримого условия. Режим выбирайте по объёму: одна понятная правка — "
            "просто напишите, несколько файлов или неясный подход — режим плана."),
    "source": "",
}

# `normal` — это КОРЗИНА: сюда падает всё, в чём не нашлось ключевых слов формы.
# Раньше она вела на ветку `trivial`, и большое исследование получало совет
# «Мелкая ясная правка — без plan/goal». Совет звучал уверенно и был неверен для
# почти любого нетривиального промпта, потому что почти любой промпт попадает сюда.
# Теперь у корзины своя ветка, которая честно говорит, что форма не определилась.
_SHAPE_TO_WHEN = {
    "trivial": "trivial",
    "normal": "normal",
    "planning": "planning",
    "goal": "goal",
    "loop": "loop",
    "workflow": "workflow",
}


def recommend_harness(prompt, target, shape=None):
    """Вернуть рекомендацию по команде запуска для текущего семейства/CLI."""
    family = target.get("family")
    if not family:
        return None
    data = catalog.load_family(family)
    harness = data.get("harness")
    if not harness:
        return None
    if shape is None:
        shape = task_shape(prompt)
    when = _SHAPE_TO_WHEN.get(shape, "normal")
    commands = {c.get("when"): c for c in harness.get("commands", [])}
    cmd = commands.get(when)
    if cmd is None and when == "normal":
        # Ветку `normal` описали только два семейства из шести. Раньше здесь стоял
        # откат на `trivial`, и остальные четыре продолжали выдавать уверенное
        # «мелкая ясная правка» на любой неопознанный промпт — тот же дефект, только
        # у другого вендора. Дефолт для неопознанной формы теперь в КОДЕ и одинаков
        # для всех: сказать, что форму определить не удалось, честнее, чем угадать.
        cmd = _UNKNOWN_SHAPE
    if cmd is None:
        cmd = commands.get("trivial")
    if not cmd:
        return None
    return {
        "shape": shape,
        "cli": harness.get("cli", data.get("display", family)),
        "command": cmd.get("command", ""),
        "title": cmd.get("title", ""),
        "why": cmd.get("why", ""),
        "source": cmd.get("source", ""),
    }
