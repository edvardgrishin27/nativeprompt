"""Определение текущей модели/CLI, которой пользуется человек.

Порядок сигналов (по убыванию надёжности):
  1. явно переданный id (--model)
  2. модель активной CLI-сессии (Codex / Claude Code)
  3. env ANTHROPIC_MODEL / OPENAI_MODEL / CODEX_MODEL
  4. ~/.claude/settings.json ("model")   / ~/.codex/config.toml (model = ...)
  5. None → спросить пользователя

Ключуем по СЕМЕЙСТВУ + поколению: незнакомый id (напр. будущий claude-opus-6)
всё равно распознаётся как семейство claude и получает family-правила.
"""

import json
import os
import re

from . import catalog


_CODEX_SESSION_ENV = ("CODEX_THREAD_ID", "CODEX_SHELL", "CODEX_CI")
_CLAUDE_SESSION_ENV = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")


def _family_from_id(model_id):
    if not model_id:
        return None
    mid = model_id.strip().lower()
    for fam in catalog.available_families():
        data = catalog.load_family(fam)
        det = data.get("detect", {})
        for pref in det.get("id_prefixes", []):
            if mid.startswith(pref.lower()):
                return fam
        for alias in det.get("aliases", []):
            if alias.lower() in mid:
                return fam
    return None


def _active_cli_family():
    """Эвристика активной поверхности без чтения значений/секретов env."""
    codex = any(os.environ.get(key) for key in _CODEX_SESSION_ENV)
    claude = any(os.environ.get(key) for key in _CLAUDE_SESSION_ENV)
    if codex == claude:
        return None
    return "openai" if codex else "claude"


def _read_claude_settings():
    path = os.path.expanduser("~/.claude/settings.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (ValueError, OSError):
        return None
    model = data.get("model")
    if isinstance(model, str) and model.strip():
        return model.strip()
    return None


def _read_codex_config():
    path = os.path.expanduser("~/.codex/config.toml")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    m = re.search(r'(?m)^\s*model\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1).strip() if m else None


def detect_model(explicit=None):
    """Вернуть dict: {model_id, family, generation, cli, source}.

    family/generation могут быть None, если модель не определилась — тогда CLI
    попросит указать её явно (--model).
    """
    # Явно заданная модель рассматривается ОТДЕЛЬНО: если она не распознана как
    # семейство — возвращаем «не определено», а не подменяем окружением.
    if explicit:
        fam = _family_from_id(explicit)
        if fam:
            data = catalog.load_family(fam)
            return {
                "model_id": explicit,
                "family": fam,
                "generation": catalog.generation_for(fam, explicit),
                "cli": data.get("display", fam),
                "surface": data.get("surface", ""),
                "source": "явно (--model)",
            }
        return {
            "model_id": explicit, "family": None, "generation": None,
            "cli": None, "surface": "", "source": "явно, не распознано",
        }

    active_family = _active_cli_family()
    cs = _read_claude_settings()
    cc = _read_codex_config()

    candidates = []
    if active_family == "openai":
        for env_key in ("CODEX_MODEL", "OPENAI_MODEL"):
            val = os.environ.get(env_key)
            if val:
                candidates.append((val.strip(), "env %s (активная сессия Codex)" % env_key))
        if cc:
            candidates.append((cc, "~/.codex/config.toml (активная сессия Codex)"))
        candidates.append(("codex", "активная сессия Codex"))
    elif active_family == "claude":
        val = os.environ.get("ANTHROPIC_MODEL")
        if val:
            candidates.append((val.strip(), "env ANTHROPIC_MODEL (активная сессия Claude Code)"))
        if cs:
            candidates.append((cs, "~/.claude/settings.json (активная сессия Claude Code)"))
        candidates.append(("claude", "активная сессия Claude Code"))
    else:
        for env_key in ("ANTHROPIC_MODEL", "OPENAI_MODEL", "CODEX_MODEL"):
            val = os.environ.get(env_key)
            if val:
                candidates.append((val.strip(), "env %s" % env_key))
        if cs:
            candidates.append((cs, "~/.claude/settings.json"))
        if cc:
            candidates.append((cc, "~/.codex/config.toml"))

    for model_id, source in candidates:
        fam = _family_from_id(model_id)
        if fam:
            data = catalog.load_family(fam)
            gen = catalog.generation_for(fam, model_id)
            return {
                "model_id": model_id,
                "family": fam,
                "generation": gen,
                "cli": data.get("display", fam),
                "surface": data.get("surface", ""),
                "source": source,
            }

    # ничего не нашли
    return {
        "model_id": None,
        "family": None,
        "generation": None,
        "cli": None,
        "surface": "",
        "source": "не определено",
    }


def resolve(explicit=None):
    """Как detect_model, но если явно задан family-алиас без версии
    ('claude', 'codex', 'gpt') — вернуть семейство без поколения."""
    res = detect_model(explicit)
    if res["family"] is None and explicit:
        fam = catalog.family_for(explicit)
        if fam:
            data = catalog.load_family(fam)
            res.update(
                {
                    "family": fam,
                    "cli": data.get("display", fam),
                    "surface": data.get("surface", ""),
                    "source": "явно (семейство)",
                    "model_id": explicit,
                }
            )
    return res
