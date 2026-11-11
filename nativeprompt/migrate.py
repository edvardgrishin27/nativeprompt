"""Переход с одной модели на другую: только разница правил и уровня усилий.

Человек, который переносит рабочий промпт на новую модель, не хочет читать
все правила заново. Ему нужно: какие советы появились, какие больше не
действуют и сменился ли уровень усилий по умолчанию. Это и печатаем. Правила
те же, что у `improve`, и выбираются тем же `scopes_for`, поэтому разница
не может разойтись с тем, что инструмент скажет про конкретный промпт.
"""

from . import catalog
from . import detect as _detect


def _правила(target):
    fam = target.get("family")
    if not fam:
        return {}
    scopes = catalog.scopes_for(fam, target.get("generation"))
    return {r["id"]: r for r in catalog.load_family(fam).get("rules", [])
            if r.get("scope", "family") == "family" or r.get("scope") in scopes}


def _effort(target):
    fam, gen = target.get("family"), target.get("generation")
    eff = catalog.load_family(fam).get("effort") if fam else None
    model = (eff or {}).get("models", {}).get(gen) if gen else None
    return model or {}


def _подпись(target):
    fam, gen = target.get("family"), target.get("generation")
    g = catalog.load_family(fam).get("generations", {}).get(gen) if fam and gen else None
    return (g or {}).get("label") or target.get("model_id") or fam or "?"


def migrate(src, dst):
    a, b = _detect.resolve(src), _detect.resolve(dst)
    if not a.get("family") or not b.get("family"):
        return {"error": "model_unknown", "from": a, "to": b}
    ra, rb = _правила(a), _правила(b)
    ea, eb = _effort(a), _effort(b)
    gen_b = catalog.load_family(b["family"]).get("generations", {}).get(b.get("generation")) or {}
    return {
        "from": {"model": _подпись(a), "generation": a.get("generation")},
        "to": {"model": _подпись(b), "generation": b.get("generation"),
               "note": gen_b.get("note"), "doc": gen_b.get("doc")},
        "added": [rb[i] for i in rb if i not in ra],
        "removed": [ra[i] for i in ra if i not in rb],
        "kept": sorted(i for i in rb if i in ra),
        "effort": {"from_default": ea.get("default"), "to_default": eb.get("default"),
                   "note": eb.get("note"), "source": eb.get("note_source")},
        "same_family": a["family"] == b["family"],
    }


def render_migrate(res):
    if res.get("error"):
        return "Модель не определилась. Пример: nativeprompt migrate --from claude-fable-5-1 --to claude-fable-5-2"
    out = ["ПЕРЕХОД: %s → %s" % (res["from"]["model"], res["to"]["model"])]
    if not res["same_family"]:
        out.append("Это разные вендоры: правила другие целиком, ниже весь новый набор.")
    if res["to"].get("note"):
        out.append("")
        out.append("О модели: %s" % res["to"]["note"])
    e = res["effort"]
    if e["from_default"] != e["to_default"]:
        out.append("")
        out.append("УРОВЕНЬ УСИЛИЙ ПО УМОЛЧАНИЮ: %s → %s. Подобранный на старой модели уровень не переносите."
                   % (e["from_default"] or "нет", e["to_default"] or "нет"))
        if e.get("note"):
            out.append("  %s" % e["note"])
            out.append("  правило: %s" % e["source"])
    out.append("")
    out.append("НОВЫЕ СОВЕТЫ (%d):" % len(res["added"]))
    for r in sorted(res["added"], key=lambda r: r.get("priority", 3)):
        out.append("+ %s — %s" % (r["id"], r["title"]))
        out.append("    правило: %s" % r["source"])
    out.append("")
    out.append("БОЛЬШЕ НЕ ДЕЙСТВУЮТ (%d):" % len(res["removed"]))
    for r in res["removed"]:
        out.append("- %s — %s" % (r["id"], r["title"]))
    if res["removed"]:
        out.append("  Если в промпте есть строки, написанные под эти советы, проверьте их на новой модели.")
    out.append("")
    out.append("Без изменений: %d общих правил." % len(res["kept"]))
    if res["to"].get("doc"):
        out.append("Страница вендора: %s" % res["to"]["doc"])
    return "\n".join(out)
