"""Сборка и рендер отчёта: было → стало + почему (со ссылкой на правило) +
как запускать. Обучающий слой инструмента."""

import textwrap

from . import catalog, detect as _detect
from .analyze import analyze, mask_code, normalize_prompt, task_shape
from .harness import recommend_harness
from .rewrite import rewrite, build_metaprompt

_ACTION_MARK = {"add": "[+]", "remove": "[-]", "restructure": "[~]", "warn": "[!]"}
_WIDTH = 76  # переносим сами: терминал рвёт длинные строки посреди слова
#: Маркер того, что инструмент к тексту не притронулся.
_UNTOUCHED_MARK = "[!]"


def _mark(finding, applied):
    """Маркер по ФАКТУ, а не по объявленному в правиле намерению.

    Раньше он читался прямо из `action`, и два always-правила с `action: add`
    (`fable5-ground-progress`, `opus48-encourage-subagents`) печатались тем же
    `[+]`, что и `opus5-concise`, который действительно дописывает «Ответь
    кратко». Маркер обещал добавление, которого не было: оба правила уходят
    только в мета-промпт. Теперь соврать он не может — знак действия получает
    лишь то правило, которое реально попало в `applied`.
    """
    if finding["id"] not in applied:
        return _UNTOUCHED_MARK
    return _ACTION_MARK.get(finding["action"], "[?]")


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
    # Нормализуем ЗДЕСЬ, а не в каждой двери: аргумент CLI приходил сырым, и
    # те же байты через `improve "…"` и через stdin давали разные отчёты —
    # пустые строки в начале дотягивали текст до порога «многочастный», и
    # XML-обёртка применялась к промпту, который по собственному критерию
    # многочастным не был.
    prompt = normalize_prompt(prompt)
    target = _detect.resolve(model)
    report = {"original": prompt, "target": target}
    if not target.get("family"):
        report["error"] = "model_unknown"
        return report
    # Форму считаем по тому же тексту, что видят детекторы: с замаскированным
    # кодом. Иначе отчёт противоречит сам себе — `analyze` уже маскировал, а
    # `task_shape` здесь читал сырой текст, и один вызов выдавал одновременно
    # «форма: trivial» и правила, которые на trivial не срабатывают.
    masked = mask_code(prompt)
    shape = task_shape(masked)
    findings = analyze(prompt, target)
    harness_rec = recommend_harness(masked, target, shape)
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
        out.append("(или --model gpt-5.6 / codex). Семейства: %s." % ", ".join(catalog.available_families()))
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
            mark = _mark(f, report["applied"])
            out.append(_wrap(f["title"], indent="      ",
                             first="%d. %s " % (i, mark)))
            out.append(_wrap(f["why"], indent="      ", first="   почему: "))
            out.append("   правило: %s" % f["source"])
    else:
        out.append("ЧТО УЛУЧШИТЬ: существенных правок правила не требуют.")
    for f in always:
        mark = _mark(f, report["applied"])
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
        if h.get("source"):
            out.append("  правило: %s" % h["source"])
        for extra in h.get("anytime") or []:
            out.append("")
            out.append("  в любой момент: %s" % extra["command"])
            out.append(_wrap(extra["title"], indent="  "))
            if extra.get("source"):
                out.append("  правило: %s" % extra["source"])

    if show_metaprompt:
        out.append("")
        out.append(bar)
        out.append("МЕТА-ПРОМПТ для «умной» переписи (вставьте своей же модели):")
        out.append(bar)
        out.append(report["metaprompt"])

    return "\n".join(out)
