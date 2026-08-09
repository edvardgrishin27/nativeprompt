"""Рекомендация «как запускать» под форму задачи и текущий CLI.

Claude Code: просто напиши / plan mode / /goal / /loop / dynamic workflow.
Codex:       просто напиши / /plan / /goal / делегировать (parallel).
Данные — из блока "harness" в rules/<family>.json (значит, тоже самообновляемы).
"""

from . import catalog
from .analyze import task_shape

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
    when = _SHAPE_TO_WHEN.get(shape, "trivial")
    commands = {c.get("when"): c for c in harness.get("commands", [])}
    cmd = commands.get(when) or commands.get("trivial")
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
