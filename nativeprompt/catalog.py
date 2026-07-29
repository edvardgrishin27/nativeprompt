"""Загрузка шпаргалок правил (rules/*.json) и выбор семейства по имени модели."""

import json
import os

_RULES_DIR = os.path.join(os.path.dirname(__file__), "rules")
_CACHE = {}


class RulesError(Exception):
    pass


def _rules_path(name):
    return os.path.join(_RULES_DIR, name + ".json")


def available_families():
    """Список доступных семейств (по файлам rules/<family>.json, кроме служебных)."""
    out = []
    for fn in sorted(os.listdir(_RULES_DIR)):
        if fn.endswith(".json") and not fn.startswith("_"):
            out.append(fn[:-5])
    return out


def load_family(family):
    """Загрузить шпаргалку семейства ('claude' | 'openai'). Кэшируется."""
    if family in _CACHE:
        return _CACHE[family]
    path = _rules_path(family)
    if not os.path.exists(path):
        raise RulesError(
            "Нет шпаргалки для семейства %r. Доступны: %s"
            % (family, ", ".join(available_families()))
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    _CACHE[family] = data
    return data


def load_sources():
    """Манифест самообновления (_sources.json)."""
    path = _rules_path("_sources")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def family_for(family_or_alias):
    """Нормализовать вход ('claude code', 'codex', 'gpt', ...) в id семейства."""
    key = (family_or_alias or "").strip().lower()
    if not key:
        return None
    for fam in available_families():
        data = load_family(fam)
        if key == fam:
            return fam
        det = data.get("detect", {})
        for alias in det.get("aliases", []):
            if key == alias.lower():
                return fam
    return None


def generation_for(family, model_id):
    """По id/имени модели найти поколение внутри семейства (например 'opus-5')."""
    if not model_id:
        return None
    data = load_family(family)
    m = model_id.strip().lower().replace(" ", "-")
    for gen_id, gen in data.get("generations", {}).items():
        for token in gen.get("match", []):
            if token.lower() in m:
                return gen_id
    return None
