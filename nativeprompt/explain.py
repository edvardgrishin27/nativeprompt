"""Сборка и рендер отчёта: было → стало + почему (со ссылкой на правило) +
как запускать. Обучающий слой инструмента."""

import textwrap

from . import detect as _detect
from .analyze import analyze, task_shape
from .harness import recommend_harness
from .rewrite import rewrite, build_metaprompt

_ACTION_MARK = {"add": "[+]", "remove": "[-]", "restructure": "[~]", "warn": "[!]"}
_WIDTH = 76  # переносим сами: терминал рвёт длинные строки посреди слова


def _wrap(text, indent="   ", first=None):
    """Перенести длинный текст по словам с отступом (для читаемости в кадре)."""
    first = indent if first is None else first
    return textwrap.fill(
        str(text), width=_WIDTH,
        initial_indent=first, subsequent_indent=indent,
        break_long_words=False, break_on_hyphens=False,
    )


def build_report(prompt, model=None):
    """Один вызов: детект модели → разбор → харнесс → перепись → мета-промпт."""
    target = _detect.resolve(model)
    report = {"original": prompt, "target": target}
    if not target.get("family"):
        report["error"] = "model_unknown"
        return report
    shape = task_shape(prompt)
    findings = analyze(prompt, target)
    harness_rec = recommend_harness(prompt, target, shape)
    rw = rewrite(prompt, target, findings, shape)
    report.update(
        {
            "shape": shape,
            "findings": findings,
            "harness": harness_rec,
            "improved": rw["improved"],
            "applied": rw["applied"],
            "metaprompt": build_metaprompt(prompt, target, findings, harness_rec),
        }
    )
    return report


def _rule(line):
    return line


def render_report(report, show_metaprompt=True):
    t = report["target"]
    out = []
    bar = "─" * 66

    if report.get("error") == "model_unknown":
        out.append("Не удалось определить модель.")
        out.append(
            "Укажите её явно: nativeprompt improve \"<промпт>\" --model claude-opus-5"
        )
        out.append("(или --model gpt-5.6 / codex). Доступно: claude, codex.")
        return "\n".join(out)

    gen = (" · " + t["generation"]) if t.get("generation") else ""
    mid = (" (" + t["model_id"] + ")") if t.get("model_id") else ""
    out.append(bar)
    out.append("МОДЕЛЬ: %s%s%s" % (t.get("cli", t["family"]), mid, gen))
    out.append("определено: %s" % t.get("source", "—"))
    if t.get("context_1m"):
        out.append("контекст: 1M (суффикс [1m] — не теряйте его при смене модели)")
    if t.get("generation_source") == "alias-unresolved":
        out.append(
            "⚠ модель задана алиасом — точная версия зависит от провайдера и плана,\n"
            "  поэтому применяю правила СЕМЕЙСТВА. Для версионных правил укажите\n"
            "  полное имя: --model claude-opus-5"
        )
    elif t.get("generation_source") == "unknown-id" and t.get("family"):
        out.append("⚠ версия модели неизвестна — применяю правила семейства")
    out.append(bar)

    findings = [f for f in report["findings"] if not f.get("always")]
    always = [f for f in report["findings"] if f.get("always")]
    out.append("")
    if findings:
        out.append("ЧТО УЛУЧШИТЬ (%d):" % len(findings))
        for i, f in enumerate(findings, 1):
            mark = _ACTION_MARK.get(f["action"], "[?]")
            out.append(_wrap(f["title"], indent="      ",
                             first="%d. %s " % (i, mark)))
            out.append(_wrap(f["why"], indent="      ", first="   почему: "))
            out.append("   правило: %s" % f["source"])
    else:
        out.append("ЧТО УЛУЧШИТЬ: существенных правок правила не требуют.")
    for f in always:
        mark = _ACTION_MARK.get(f["action"], "[?]")
        out.append(_wrap(f["title"], indent="    ", first="%s " % mark))
        out.append("    правило: %s" % f["source"])

    out.append("")
    out.append(bar)
    out.append("УЛУЧШЕННЫЙ ПРОМПТ (детерминированная правка):")
    out.append(bar)
    out.append(report["improved"])
    out.append(bar)

    h = report.get("harness")
    if h:
        out.append("")
        out.append("КАК ЗАПУСКАТЬ (%s) — форма задачи: %s" % (h["cli"], h["shape"]))
        out.append("  → %s" % h["command"])
        out.append(_wrap(h["title"], indent="  "))
        out.append(_wrap(h["why"], indent="  ", first="  почему: "))
        out.append("  правило: %s" % h["source"])

    if show_metaprompt:
        out.append("")
        out.append(bar)
        out.append("МЕТА-ПРОМПТ для «умной» переписи (вставьте своей же модели):")
        out.append(bar)
        out.append(report["metaprompt"])

    return "\n".join(out)
