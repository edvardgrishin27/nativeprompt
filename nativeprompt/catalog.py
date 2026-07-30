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


def scopes_for(family, generation):
    """Какие scope-ключи применимы к этому поколению.

    Вендор иногда прямо пишет, что правила одной модели применимы к другой
    (Mythos 5 ключуется на страницу Fable 5; guidance Opus 4.7 применим к 4.8).
    Такие связи описаны полем "rules_of" в generations — здесь мы их
    разворачиваем, чтобы правило с scope="fable-5" сработало и для mythos-5.
    """
    if not generation:
        return set()
    data = load_family(family)
    gens = data.get("generations", {})
    out, cur, guard = {generation}, generation, 0
    while guard < 5:
        parent = (gens.get(cur) or {}).get("rules_of")
        if not parent or parent in out:
            break
        out.add(parent)
        cur = parent
        guard += 1
    return out


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
