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
    all_cmds = harness.get("commands", [])
    # `anytime` — советы, не привязанные к форме задачи (/rewind, /effort и т. п.).
    # Раньше они пропадали дважды: словарь ниже схлопывал одинаковые `when`, оставляя
    # последний, а сама ветка `anytime` из `_SHAPE_TO_WHEN` недостижима. То есть у
    # четырёх семейств по два-три сорсенных совета вендора не показывались никогда.
    anytime = [c for c in all_cmds if c.get("when") == "anytime"]
    commands = {c.get("when"): c for c in all_cmds if c.get("when") != "anytime"}
    # Нет ветки под эту форму — говорим, что форму не определили. Раньше здесь
    # стоял откат на `trivial`, и семейства без ветки `normal` выдавали уверенное
    # «мелкая ясная правка» на любой неопознанный промпт. Откат убран целиком:
    # недостающая ветка не должна превращаться в уверенный совет ни при каких
    # условиях, включая семейство, которого сегодня ещё нет в наборе.
    cmd = commands.get(when) or _UNKNOWN_SHAPE
    return {
        "shape": shape,
        "cli": harness.get("cli", data.get("display", family)),
        "command": cmd.get("command", ""),
        "title": cmd.get("title", ""),
        "why": cmd.get("why", ""),
        "source": cmd.get("source", ""),
        "anytime": [
            {"command": c.get("command", ""), "title": c.get("title", ""),
             "source": c.get("source", "")}
            for c in anytime
        ],
    }
