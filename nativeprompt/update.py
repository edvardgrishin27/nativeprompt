"""Самообновление шпаргалки.

Тянет канонические .md/llms.txt страницы вендоров (манифест rules/_sources.json),
считает sha256 и сравнивает со снапшотом rules/_snapshot.json.

ВАЖНО: правила (rules/*.json) НЕ переписываются автоматически — это делает человек,
когда CI/локальный `update` покажет, что офиц. доки изменились (тогда открывается PR
на ревью). Так шпаргалка остаётся детерминированной и проверяемой, но не устаревает.
"""

import difflib
import hashlib
import json
import os
import re
import urllib.error
import urllib.request

from . import catalog

_RULES_DIR = os.path.join(os.path.dirname(__file__), "rules")
_SNAPSHOT = os.path.join(_RULES_DIR, "_snapshot.json")
# Снимки ТЕКСТА доков (а не только хэши) — чтобы показывать, ЧТО именно
# изменилось у вендора, а не просто «что-то изменилось». ~0.5 МБ на все доки.
# В пакет не попадают (package-data только rules/*.json) — нужны в репозитории.
_DOCS_DIR = os.path.join(_RULES_DIR, "_docs")
_UA = "nativeprompt-update/0.1 (+https://github.com/edvardgrishin27/nativeprompt)"


def _doc_path(url):
    """Безопасное имя файла для снимка текста дока."""
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", url.split("://", 1)[-1]).strip("-")
    return os.path.join(_DOCS_DIR, slug[:120] + ".txt")


def _read_doc_snapshot(url):
    path = _doc_path(url)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _write_doc_snapshot(url, text):
    os.makedirs(_DOCS_DIR, exist_ok=True)
    with open(_doc_path(url), "w", encoding="utf-8") as f:
        f.write(text)


def doc_diff(url, new_text, context=2, max_lines=60):
    """Unified diff «было → стало» по тексту дока. None, если сравнить не с чем."""
    old = _read_doc_snapshot(url)
    if old is None:
        return None
    if old == new_text:
        return ""
    lines = list(
        difflib.unified_diff(
            old.splitlines(), new_text.splitlines(),
            fromfile="было", tofile="стало", lineterm="", n=context,
        )
    )
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["… (показаны первые %d строк изменений)" % max_lines]
    return "\n".join(lines)


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
        text = payload.decode("utf-8", "replace")
        diff = None

        # Источник истины — СНИМОК ТЕКСТА, если он есть: тогда статус и diff
        # заведомо согласованы. Хэш из _snapshot.json — только фолбэк для
        # доков, снимок текста которых ещё не сохранён.
        prev_text = _read_doc_snapshot(url)
        if prev_text is not None:
            if prev_text == text:
                status, unchanged = "unchanged", unchanged + 1
            else:
                status, changed = "changed", changed + 1
                diff = doc_diff(url, text)   # ЧТО именно изменилось у вендора
        else:
            prev = snap.get(url)
            if prev is None:
                status, new = "new", new + 1
            elif prev != digest:
                status, changed = "changed", changed + 1
            else:
                status, unchanged = "unchanged", unchanged + 1
        new_snap[url] = digest
        row = {"family": fam, "url": url, "status": status}
        if diff:
            row["diff"] = diff
        results.append(row)
        if write:
            _write_doc_snapshot(url, text)

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


def render_update(res, show_diff=False):
    out = []
    order = {"changed": 0, "new": 1, "unreachable": 2, "unchanged": 3}
    mark = {"changed": "[изменилось]", "new": "[новое]", "unreachable": "[недоступно]", "unchanged": "[без изменений]"}
    for r in sorted(res["results"], key=lambda x: order.get(x["status"], 9)):
        line = "%-18s %s  %s" % (mark.get(r["status"], r["status"]), r["family"], r["url"])
        if r.get("detail"):
            line += "  (%s)" % r["detail"]
        out.append(line)
        if show_diff and r.get("diff"):
            out.append("")
            out.append("  ── что изменилось у вендора ──")
            for dl in r["diff"].splitlines():
                out.append("  " + dl)
            out.append("")
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
