#!/usr/bin/env python3
"""Демо-контраст: ОДИН и тот же «сырой» промпт улучшается ПО-РАЗНОМУ под разные
модели/CLI — потому что у каждой своя официальная грамматика.

Запуск:  python3 examples/contrast_demo.py
Это и есть кадр для ролика: слева Claude Code, справа Codex.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nativeprompt.explain import build_report  # noqa: E402

ROUGH = (
    "Не мог бы ты пожалуйста ОБЯЗАТЕЛЬНО починить баг в логине, "
    "думай пошагово и обязательно перепроверь себя. Покажи только самое важное."
)


def block(title, report):
    print("\n" + "#" * 70)
    print("# " + title)
    print("#" * 70)
    t = report["target"]
    print("Модель: %s (%s)" % (t.get("cli"), t.get("model_id")))
    print("\n-- было --\n" + report["original"])
    print("\n-- стало (детерминированная правка) --\n" + report["improved"])
    print("\n-- почему (правила вендора) --")
    for f in report["findings"]:
        if f.get("always"):
            continue
        print("  • %s\n    %s" % (f["title"], f["source"]))
    h = report["harness"]
    print("\n-- как запускать (%s) --" % h["cli"])
    print("  → %s  (форма: %s)" % (h["command"], h["shape"]))


def main():
    print("СЫРОЙ ПРОМПТ:\n" + ROUGH)
    block("CLAUDE CODE (Opus 5)", build_report(ROUGH, model="claude-opus-5"))
    block("CODEX (GPT-5.6)", build_report(ROUGH, model="gpt-5.6"))
    print("\n" + "=" * 70)
    print("Тот же промпт — разные правки: Claude оставляет 'думай пошагово' и убирает")
    print("'перепроверь себя' (Opus 5 верифицирует сам); Codex, наоборот, ВЫРЕЗАЕТ CoT.")
    print("Каждая правка — со ссылкой на официальное правило вендора.")


if __name__ == "__main__":
    main()
