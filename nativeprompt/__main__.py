"""CLI: nativeprompt <команда>.

  improve "<промпт>" [--model M] [--json] [--no-metaprompt] [--verify]
                                                              переписать + объяснить
  detect [--model M]                                          какая модель определилась
  rules [семейство]                                           показать правила + источники
  update [--write] [--timeout N]                              сверить свежесть офиц. доков
"""

import argparse
import json
import sys

from . import __version__, catalog, detect as _detect
from .analyze import normalize_prompt
from .explain import build_report, render_report, render_verify, verify_delta, nothing_to_do
from . import update as _update


def _force_utf8_io():
    """Вывод всегда в UTF-8, независимо от системной кодировки консоли.

    На Windows stdout по умолчанию идёт в системной ANSI (у русской локали cp1251).
    Из-за этого `--json` нарушал спецификацию JSON, которая требует UTF-8, и обычный
    разбор падал. Хуже: символы вне cp1251 — стрелка «→», угловые кавычки «‹›» из
    плейсхолдеров — роняли команду целиком с UnicodeEncodeError, а не портили текст.

    `errors="replace"` оставлен намеренно: даже на экзотической консоли команда обязана
    доработать до конца, а не упасть на одном символе.
    """
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):      # поток подменён или не поддерживает
                pass


def _read_prompt(arg):
    # `arg.strip()`, а не `arg`: аргумент из одних пробелов — truthy, и такой
    # вызов доходил до отчёта. Промпта в нём нет, а на выходе получался
    # «улучшенный промпт», состоящий из одной нашей же добавки. Из stdin то же
    # самое отсеивалось всегда — теперь обе двери одинаковые.
    if arg and arg.strip():
        return arg
    if not sys.stdin.isatty():
        # `strip()` здесь срезал ведущий отступ первой строки — маркер
        # отступного блока кода. И это была ШТАТНАЯ дверь: SKILL.md предписывает
        # передавать промпт именно через stdin, так что исправление 0.3.1 в
        # обычном сценарии просто не работало.
        data = normalize_prompt(sys.stdin.read())
        if data.strip():
            return data
    return None


def cmd_improve(args):
    prompt = _read_prompt(args.prompt)
    if not prompt:
        print("Дайте промпт: nativeprompt improve \"<текст>\"  (или через stdin).", file=sys.stderr)
        return 2
    report = build_report(prompt, model=args.model)
    # Самопроверка — отдельный шаг за флагом. Без флага её нет вовсе: ни
    # второго прогона, ни лишней строки в выводе, ни нового ключа в --json.
    # У людей вызов хука уже прописан в settings.json, и он обязан работать
    # ровно как раньше.
    # На отчёте с ошибкой (модель не опознана) разбора не было вовсе, и пустые
    # корзины прочитались бы как «инструмент ничего не внёс». Молчим — ровно
    # так же, как молчит текстовая ветка и как убран meta.
    delta = verify_delta(report) if (args.verify and not report.get("error")) else None
    if args.json:
        out = dict(report)                        # не мутируем отчёт
        if delta is not None:
            out["verify"] = delta
        # Скилл ходит через --json и по нему решает, выполнять ли мета-промпт.
        # Без этого ключа ему нечем свериться с CLI, и два пути расходятся.
        if not report.get("error"):
            out["nothing_to_do"] = nothing_to_do(report)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if not report.get("error") else 1
    print(render_report(report, show_metaprompt=not args.no_metaprompt))
    if delta is not None and not report.get("error"):
        print(render_verify(delta))
    return 0 if not report.get("error") else 1


def cmd_detect(args):
    res = _detect.resolve(args.model)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0
    if not res.get("family"):
        print("Модель не определена. Задайте --model claude-opus-5 / gpt-5.6 / codex.")
        print("Сигналы: env ANTHROPIC_MODEL/OPENAI_MODEL, ~/.claude/settings.json, ~/.codex/config.toml.")
        return 1
    gen = (" · " + res["generation"]) if res.get("generation") else ""
    print("Модель: %s%s" % (res.get("model_id") or res["family"], gen))
    print("Семейство/CLI: %s (%s)" % (res["family"], res.get("cli", "")))
    print("Определено: %s" % res.get("source", "—"))
    return 0


def cmd_rules(args):
    fam = args.family
    if fam:
        fam = catalog.family_for(fam) or fam
        families = [fam]
    else:
        families = catalog.available_families()
    for family in families:
        try:
            data = catalog.load_family(family)
        except catalog.RulesError as e:
            print(str(e), file=sys.stderr)
            return 1
        print("=" * 66)
        print("%s — %s  (версия правил: %s)" % (data.get("display", family), data.get("vendor", ""), data.get("rules_version", "?")))
        print(data.get("surface", ""))
        print("=" * 66)

        gens = data.get("generations", {})
        if gens:
            print("\nМОДЕЛИ, КОТОРЫЕ ИНСТРУМЕНТ ЗНАЕТ (%d):" % len(gens))
            own = [g for g, v in gens.items() if v.get("doc")]
            for gid, g in gens.items():
                if g.get("doc"):
                    mark, tail = "★", "своя страница правил у вендора"
                elif g.get("rules_of"):
                    mark, tail = "↳", "правила от %s (так решил вендор)" % g["rules_of"]
                else:
                    mark, tail = "·", "своей страницы нет — правила семейства"
                print("  %s %-12s %-22s %s" % (mark, gid, g.get("label", ""), tail))
            print("  ─ ★ %d из %d моделей имеют собственные правила; остальные работают"
                  % (len(own), len(gens)))
            print("    на правилах семейства — они НЕ выдуманы, их просто не публиковал вендор.")
            print("    Незнакомая новая модель тоже получит правила семейства, а не откажет.")

        print("\nПРАВИЛА:")
        for r in data.get("rules", []):
            scope = "" if r.get("scope") == "family" else ("  [%s]" % r["scope"])
            print("• %s%s" % (r["title"], scope))
            print("  %s" % r["source"])
        h = data.get("harness")
        if h:
            print("\nХАРНЕСС (%s): когда какая команда" % h.get("cli", ""))
            for c in h.get("commands", []):
                print("  [%s] %s → %s" % (c.get("when"), c.get("title"), c.get("command")))
                print("      %s" % c.get("source"))
        print("")
    return 0


def cmd_update(args):
    res = _update.update(write=args.write, timeout=args.timeout)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(_update.render_update(res, show_diff=args.diff))
    # ненулевой код, если нужны действия (для CI)
    return 1 if res["summary"]["action_needed"] and not args.write else 0


def build_parser():
    p = argparse.ArgumentParser(
        prog="nativeprompt",
        description="Перепиши промпт под родной диалект твоей модели (Claude Code / Codex) по офиц. правилам вендора — и объясни почему.",
    )
    p.add_argument("--version", action="version", version="nativeprompt " + __version__)
    sub = p.add_subparsers(dest="command")

    pi = sub.add_parser("improve", help="переписать промпт под текущую модель + объяснить")
    pi.add_argument("prompt", nargs="?", help="текст промпта (или из stdin)")
    pi.add_argument("--model", help="целевая модель: claude-opus-5 / gpt-5.6 / codex …")
    pi.add_argument("--json", action="store_true", help="выдать отчёт как JSON")
    pi.add_argument("--no-metaprompt", action="store_true", help="без блока мета-промпта")
    pi.add_argument("--verify", action="store_true",
                    help="прогнать детекторы по собственному результату: закрыто / оставлено вам / внесено инструментом")
    pi.set_defaults(func=cmd_improve)

    pd = sub.add_parser("detect", help="показать, какая модель определилась")
    pd.add_argument("--model", help="переопределить явно")
    pd.add_argument("--json", action="store_true")
    pd.set_defaults(func=cmd_detect)

    pr = sub.add_parser("rules", help="показать правила + источники")
    pr.add_argument("family", nargs="?", help="claude | codex | gemini | grok | kimi | qwen (по умолчанию — все)")
    pr.set_defaults(func=cmd_rules)

    pu = sub.add_parser("update", help="сверить свежесть офиц. доков (self-update)")
    pu.add_argument("--write", action="store_true", help="записать снимки (после ревью правил)")
    pu.add_argument("--diff", action="store_true",
                    help="показать, ЧТО именно изменилось в доке вендора (было → стало)")
    pu.add_argument("--timeout", type=int, default=20)
    pu.add_argument("--json", action="store_true")
    pu.set_defaults(func=cmd_update)

    return p


def main(argv=None):
    _force_utf8_io()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
