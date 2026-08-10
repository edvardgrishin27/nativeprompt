"""nativeprompt — перепиши промпт на РОДНОЙ диалект той модели/CLI, которой ты
реально пользуешься (Claude Code, Codex, Gemini CLI, Grok, Kimi, Qwen), строго по ОФИЦИАЛЬНЫМ правилам вендора,
и объясни почему.

Zero-deps, stdlib-only, детерминированное ядро. См. README.md.
"""

__version__ = "0.3.5"

from .catalog import load_family, available_families, RulesError
from .detect import detect_model
from .analyze import analyze, task_shape
from .harness import recommend_harness
from .rewrite import rewrite, build_metaprompt
from .explain import build_report, render_report

__all__ = [
    "__version__",
    "load_family",
    "available_families",
    "RulesError",
    "detect_model",
    "analyze",
    "task_shape",
    "recommend_harness",
    "rewrite",
    "build_metaprompt",
    "build_report",
    "render_report",
]
