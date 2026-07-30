"""Самообновление шпаргалки.

Тянет канонические .md/llms.txt страницы вендоров (манифест rules/_sources.json),
считает sha256 и сравнивает со снапшотом rules/_snapshot.json.

ВАЖНО: правила (rules/*.json) НЕ переписываются автоматически — это делает человек,
когда CI/локальный `update` покажет, что офиц. доки изменились (тогда открывается PR
на ревью). Так шпаргалка остаётся детерминированной и проверяемой, но не устаревает.
"""

import hashlib
import json
import os
import urllib.error
import urllib.request

from . import catalog

_RULES_DIR = os.path.join(os.path.dirname(__file__), "rules")
_SNAPSHOT = os.path.join(_RULES_DIR, "_snapshot.json")
_UA = "nativeprompt-update/0.1 (+https://github.com/edvardgrishin27/nativeprompt)"


def _load_snapshot():
    if not os.path.exists(_SNAPSHOT):
        return {}
    try:
        with open(_SNAPSHOT, "r", encoding="utf-8") as f:
            return json.load(f)
    except (ValueError, OSError):
        return {}


def _save_snapshot(snap):
    with open(_SNAPSHOT, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        return True, data
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as e:
        return False, str(e)


def _all_urls():
    sources = catalog.load_sources()
    urls = []
    for fam, info in sources.get("families", {}).items():
        for u in info.get("docs", []):
            urls.append((fam, u))
        idx = info.get("index")
        if idx:
            urls.append((fam, idx))
    return urls


def update(write=False, timeout=20):
    """Проверить свежесть офиц. доков. Вернуть {results, summary}.

    write=False (по умолчанию) — только сравнение (dry-run), снапшот не трогаем.
    write=True — записать новые хэши в _snapshot.json (после ревью правил).
    """
    snap = _load_snapshot()
    new_snap = dict(snap)
    results = []
    changed = new = unreachable = unchanged = 0

    for fam, url in _all_urls():
        ok, payload = _fetch(url, timeout=timeout)
        if not ok:
            results.append({"family": fam, "url": url, "status": "unreachable", "detail": payload})
            unreachable += 1
            continue
        digest = hashlib.sha256(payload).hexdigest()
        prev = snap.get(url)
        if prev is None:
            status = "new"
            new += 1
        elif prev != digest:
            status = "changed"
            changed += 1
        else:
            status = "unchanged"
            unchanged += 1
        new_snap[url] = digest
        results.append({"family": fam, "url": url, "status": status})

    if write:
        _save_snapshot(new_snap)

    summary = {
        "changed": changed,
        "new": new,
        "unchanged": unchanged,
        "unreachable": unreachable,
        "total": len(results),
        "action_needed": changed > 0 or new > 0,
        "wrote_snapshot": write,
    }
    return {"results": results, "summary": summary}


def render_update(res):
    out = []
    order = {"changed": 0, "new": 1, "unreachable": 2, "unchanged": 3}
    mark = {"changed": "[изменилось]", "new": "[новое]", "unreachable": "[недоступно]", "unchanged": "[без изменений]"}
    for r in sorted(res["results"], key=lambda x: order.get(x["status"], 9)):
        line = "%-18s %s  %s" % (mark.get(r["status"], r["status"]), r["family"], r["url"])
        if r.get("detail"):
            line += "  (%s)" % r["detail"]
        out.append(line)
    s = res["summary"]
    out.append("")
    out.append(
        "Итог: изменилось %d, новых %d, без изменений %d, недоступно %d (из %d)."
        % (s["changed"], s["new"], s["unchanged"], s["unreachable"], s["total"])
    )
    if s["action_needed"]:
        out.append(
            "→ Офиц. доки изменились. Сверьте правила rules/*.json с источником и "
            "обновите их вручную. Затем зафиксируйте: nativeprompt update --write."
        )
        out.append(
            "  (в CI эта команда возвращает ненулевой код — job падает и вы видите,"
            " что пора сверяться)"
        )
    else:
        out.append("→ Правила соответствуют последним офиц. докам.")
    return "\n".join(out)
