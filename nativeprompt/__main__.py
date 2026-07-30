"""CLI: nativeprompt <команда>.

  improve "<промпт>" [--model M] [--json] [--no-metaprompt]   переписать + объяснить
  detect [--model M]                                          какая модель определилась
  rules [claude|codex]                                        показать правила + источники
  update [--write] [--timeout N]                              сверить свежесть офиц. доков
"""

import argparse
import json
import sys

from . import __version__, catalog, detect as _detect
from .explain import build_report, render_report
from . import update as _update


def _read_prompt(arg):
    if arg:
        return arg
    if not sys.stdin.isatty():
        data = sys.stdin.read().strip()
        if data:
            return data
    return None


def cmd_improve(args):
    prompt = _read_prompt(args.prompt)
    if not prompt:
        print("Дайте промпт: nativeprompt improve \"<текст>\"  (или через stdin).", file=sys.stderr)
        return 2
    report = build_report(prompt, model=args.model)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not report.get("error") else 1
    print(render_report(report, show_metaprompt=not args.no_metaprompt))
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
    pi.set_defaults(func=cmd_improve)

    pd = sub.add_parser("detect", help="показать, какая модель определилась")
    pd.add_argument("--model", help="переопределить явно")
    pd.add_argument("--json", action="store_true")
    pd.set_defaults(func=cmd_detect)

    pr = sub.add_parser("rules", help="показать правила + источники")
    pr.add_argument("family", nargs="?", help="claude | codex (по умолчанию — все)")
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
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
