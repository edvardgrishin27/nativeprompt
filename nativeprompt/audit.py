"""Проверка файлов постоянных инструкций: CLAUDE.md, AGENTS.md, скиллы, агенты, память.

Зачем отдельный режим. `improve` разбирает текст как ЗАДАЧУ: у задачи нет
контракта результата, нет файла, нет проверки — и всё это советы по делу. У
файла инструкций задачи нет, и те же советы там шум. Зато вендор Fable 5.2
прямо просит перед переходом перечитать именно эти файлы: в них копятся
«никогда», постоянное «запускай субагентов», «отвечай без раздумий»,
жёсткий счёт слов. Такие строки находятся детекторами фраз, и у каждой есть
строка файла — её и печатаем, как компилятор: `файл:строка: id`.

Строка `nativeprompt: ignore <id>` в файле (например в HTML-комментарии)
выключает правило для этого файла: запрет по делу человек помечает один раз,
и CI на нём больше не падает.
"""

import os
import re

from . import detect as _detect
from .analyze import analyze, normalize_prompt

#: Детекторы фраз, которые имеют смысл в постоянных инструкциях. Детекторы
#: задачи («нет контракта», «задача длинная», «про код») сюда не входят.
AUDIT_CHECKS = frozenset({
    "think_less", "approval_rule", "absolute_rule", "delegate_push",
    "token_budget", "treat_done", "hard_style_limit", "discourage_tools",
    "hold_findings", "think_hard", "keep_going", "forced_cot",
    "show_thinking", "antiformatting",
})

#: Имена файлов инструкций у шести харнессов, которые знает инструмент.
_ИМЕНА = {"claude.md", "claude.local.md", "agents.md", "gemini.md", "qwen.md", "skill.md"}
#: Каталоги, где каждый .md — инструкция: агенты, команды, правила, память.
_КАТАЛОГИ = {"agents", "commands", "rules", "memory", "skills"}
_ПРОПУСК = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".tox"}
_ПРЕДЕЛ_ФАЙЛОВ = 500
_ПРЕДЕЛ_РАЗМЕРА = 1_000_000
_IGNORE = re.compile(r"nativeprompt:\s*ignore\s+([\w.,\s-]+)", re.I)


def _это_инструкция(путь):
    имя = os.path.basename(путь).lower()
    if имя in _ИМЕНА:
        return True
    if not имя.endswith(".md"):
        return False
    части = {ч.lower() for ч in путь.replace("\\", "/").split("/")[:-1]}
    return bool(части & _КАТАЛОГИ)


def collect_files(paths):
    """Файлы инструкций из путей: файл берём как есть, каталог обходим."""
    out = []
    for путь in paths:
        if os.path.isfile(путь):
            out.append(путь)
            continue
        for корень, каталоги, файлы in os.walk(путь):
            каталоги[:] = sorted(к for к in каталоги if к not in _ПРОПУСК)
            for имя in sorted(файлы):
                полный = os.path.join(корень, имя)
                if _это_инструкция(полный):
                    out.append(полный)
                    if len(out) >= _ПРЕДЕЛ_ФАЙЛОВ:
                        return out
    return out


def _ignored(text):
    ids = set()
    for m in _IGNORE.finditer(text):
        ids.update(i.strip() for i in re.split(r"[,\s]+", m.group(1)) if i.strip())
    return ids


def audit_text(text, target, path="<stdin>"):
    """Находки по одному тексту: по строке на каждое место, где сработало правило."""
    text = normalize_prompt(text)
    выкл = _ignored(text)
    out = []
    for f in analyze(text, target):
        if f.get("check") not in AUDIT_CHECKS or f["id"] in выкл:
            continue
        for у in f.get("evidence") or []:
            out.append({
                "file": path, "line": у["line"], "text": у["text"], "match": у["match"],
                "id": f["id"], "title": f["title"], "why": f["why"], "unless": f["unless"],
                "action": f["action"], "priority": f["priority"], "source": f["source"],
            })
    return out


def audit_paths(paths, model=None, target=None):
    if target is None:
        target = _detect.resolve(model)
    if not target.get("family"):
        return {"error": "model_unknown", "target": target, "files": [], "findings": []}
    файлы = collect_files(paths)
    находки, пропущены = [], []
    for путь in файлы:
        try:
            if os.path.getsize(путь) > _ПРЕДЕЛ_РАЗМЕРА:
                пропущены.append({"file": путь, "reason": "больше 1 МБ"})
                continue
            with open(путь, encoding="utf-8") as fh:
                текст = fh.read()
        except (OSError, UnicodeDecodeError) as e:
            пропущены.append({"file": путь, "reason": str(e)})
            continue
        находки.extend(audit_text(текст, target, путь))
    находки.sort(key=lambda x: (x["priority"], x["file"], x["line"]))
    return {"target": target, "files": файлы, "skipped": пропущены, "findings": находки}


def render_audit(res):
    t = res["target"]
    if res.get("error"):
        return "Модель не определилась. Назовите её: nativeprompt audit <путь> --model <id>."
    модель = t.get("model_id") or t.get("generation") or t.get("family")
    out = ["nativeprompt audit · модель: %s · файлов: %d · находок: %d"
           % (модель, len(res["files"]), len(res["findings"]))]
    if not res["files"]:
        out.append("Файлов инструкций не нашёл: CLAUDE.md, AGENTS.md, SKILL.md, "
                   ".md в agents/, commands/, rules/, memory/, skills/.")
    источники = {}
    for f in res["findings"]:
        out.append("%s:%d: %s — %s" % (f["file"], f["line"], f["id"], f["title"]))
        out.append("    «%s»" % f["text"])
        источники.setdefault(f["id"], f)
    if источники:
        out.append("")
        out.append("ПОЧЕМУ И КОГДА СОВЕТ НЕ ПОДХОДИТ:")
        for i, f in источники.items():
            out.append("%s: %s" % (i, f["why"]))
            if f.get("unless"):
                out.append("    не подходит, если: %s" % f["unless"])
            out.append("    правило: %s" % f["source"])
        out.append("")
        out.append("Запрет по делу? Допишите в файл «nativeprompt: ignore <id>» "
                   "(например, в HTML-комментарии), и правило там замолчит.")
    for п in res.get("skipped") or []:
        out.append("пропущен %s: %s" % (п["file"], п["reason"]))
    return "\n".join(out)
