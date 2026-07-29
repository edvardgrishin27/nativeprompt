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


_CODEX_SESSION_ENV = ("CODEX_THREAD_ID", "CODEX_SHELL", "CODEX_CI", "CODEX_SANDBOX")
_CLAUDE_SESSION_ENV = ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")

# Суффикс окна контекста 1M: "opus[1m]", "claude-opus-5[1m]".
# Claude Code сам срезает его перед матчингом модели — делаем так же, но
# ЗАПОМИНАЕМ факт, чтобы не подтолкнуть пользователя к потере 1M-контекста.
_SUFFIX_1M = re.compile(r"^(?P<base>.+?)\[1m\]$", re.I)

# Алиасы Claude Code, за которыми стоит НЕизвестная нам версия: какая именно
# модель откликнется — зависит от провайдера, плана и ANTHROPIC_DEFAULT_*.
# Поэтому поколение из них НЕ выводим (честнее, чем угадать).
_UNRESOLVED_ALIASES = {"opus", "sonnet", "haiku", "fable", "best", "opusplan", "default"}


def _split_1m(model_id):
    """('opus[1m]') → ('opus', True). Вернуть (base_id, context_1m)."""
    if not model_id:
        return model_id, False
    m = _SUFFIX_1M.match(model_id.strip())
    if m:
        return m.group("base").strip(), True
    return model_id.strip(), False


def _family_from_id(model_id):
    if not model_id:
        return None
    mid, _ = _split_1m(model_id)
    mid = mid.lower()
    if mid in _UNRESOLVED_ALIASES:
        return "claude"  # все эти алиасы — из Claude Code
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


def _build_result(model_id, source):
    """Собрать результат детекта с нормализацией суффикса и честной пометкой
    о том, откуда взялось поколение."""
    fam = _family_from_id(model_id)
    if not fam:
        return None
    base, ctx_1m = _split_1m(model_id)
    data = catalog.load_family(fam)
    if base.lower() in _UNRESOLVED_ALIASES:
        gen, gen_source = None, "alias-unresolved"
    else:
        gen = catalog.generation_for(fam, base)
        gen_source = "model-id" if gen else "unknown-id"
    return {
        "model_id": model_id,
        "model_id_base": base,
        "context_1m": ctx_1m,
        "family": fam,
        "generation": gen,
        "generation_source": gen_source,
        "cli": data.get("display", fam),
        "surface": data.get("surface", ""),
        "source": source,
    }


def _active_cli_family():
    """Эвристика активной поверхности без чтения значений/секретов env."""
    codex = any(os.environ.get(key) for key in _CODEX_SESSION_ENV)
    claude = any(os.environ.get(key) for key in _CLAUDE_SESSION_ENV)
    if codex == claude:
        return None
    return "openai" if codex else "claude"


def _model_from_settings_file(path):
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


def _read_claude_settings():
    """Каскад настроек Claude Code (ближе к проекту — выше приоритет).

    .claude/settings.local.json и .claude/settings.json ищутся от текущей папки
    вверх до корня, затем ~/.claude/settings.json. В VS Code это ГЛАВНЫЙ источник:
    переменной ANTHROPIC_MODEL там нет, а пикер /model пишет модель в settings.
    Возвращает (model_id, откуда) или (None, None).
    """
    try:
        cur = os.path.abspath(os.getcwd())
    except OSError:
        cur = None
    home_dir = os.path.expanduser("~")
    seen = set()
    while cur and cur not in seen:
        seen.add(cur)
        if cur == home_dir:
            break  # ~/.claude/settings.json — это не «проект», он ниже отдельно
        for name in ("settings.local.json", "settings.json"):
            path = os.path.join(cur, ".claude", name)
            model = _model_from_settings_file(path)
            if model:
                return model, os.path.join(".claude", name) + " (проект)"
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    home = os.path.expanduser("~/.claude/settings.json")
    model = _model_from_settings_file(home)
    if model:
        return model, "~/.claude/settings.json"
    return None, None


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
        res = _build_result(explicit, "явно (--model)")
        if res:
            return res
        return {
            "model_id": explicit, "model_id_base": explicit, "context_1m": False,
            "family": None, "generation": None, "generation_source": "unknown-id",
            "cli": None, "surface": "", "source": "явно, не распознано",
        }

    active_family = _active_cli_family()
    cs, cs_where = _read_claude_settings()
    cc = _read_codex_config()
    ide = " · VS Code" if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "claude-vscode" else ""

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
            candidates.append((val.strip(), "env ANTHROPIC_MODEL (сессия Claude Code%s)" % ide))
        if cs:
            candidates.append((cs, "%s (сессия Claude Code%s)" % (cs_where, ide)))
        candidates.append(("claude", "активная сессия Claude Code%s" % ide))
    else:
        for env_key in ("ANTHROPIC_MODEL", "OPENAI_MODEL", "CODEX_MODEL"):
            val = os.environ.get(env_key)
            if val:
                candidates.append((val.strip(), "env %s" % env_key))
        if cs:
            candidates.append((cs, cs_where))
        if cc:
            candidates.append((cc, "~/.codex/config.toml"))

    for model_id, source in candidates:
        res = _build_result(model_id, source)
        if res:
            return res

    # ничего не нашли
    return {
        "model_id": None,
        "model_id_base": None,
        "context_1m": False,
        "family": None,
        "generation": None,
        "generation_source": "unknown-id",
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
