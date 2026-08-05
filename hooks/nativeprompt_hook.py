#!/usr/bin/env python3
"""UserPromptSubmit-хук для Claude Code: на КАЖДЫЙ промпт подмешивает улучшенную
версию + правила текущей модели (additionalContext). Сам текст промпта НЕ заменяет
(ограничение Claude Code) — Claude видит рядом оригинал и улучшенную версию.

Дизайн: молчит на коротких/хороших промптах (не засоряет). Любая ошибка → тихо
ничего (никогда не ломает отправку промпта).

Подключение: см. README-блок ниже / settings.json.
"""

import json
import os
import sys


def _find_package():
    """Найти пакет nativeprompt, не завися от машины автора.

    Порядок: уже установлен (pip/pipx) → каталог этого хука (клон репозитория) →
    NATIVEPROMPT_HOME → CLAUDE_PROJECT_DIR. Хук должен работать у любого,
    кто склонировал репозиторий куда угодно.
    """
    try:  # уже установлен в окружение
        import nativeprompt  # noqa: F401
        return None
    except ImportError:
        pass
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # <repo>/hooks/.. = <repo>
    candidates = [
        here,
        os.environ.get("NATIVEPROMPT_HOME", ""),
        os.environ.get("CLAUDE_PROJECT_DIR", ""),
    ]
    for c in candidates:
        if c and os.path.isdir(os.path.join(os.path.expanduser(c), "nativeprompt")):
            return os.path.expanduser(c)
    return None


def _force_utf8_stdio():
    """Claude Code шлёт хуку UTF-8; на Windows stdin/stdout берут ANSI-кодовую
    страницу (cp1251 на русской локали). Без этого русский промпт приходит
    мохибейком, регулярки-детекторы по нему не срабатывают, и хук молча
    возвращает пустоту — то есть выглядит рабочим, ничего не делая.
    """
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def main():
    _force_utf8_stdio()
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0
    prompt = (data.get("prompt") or data.get("user_prompt") or "").strip()
    if len(prompt) < 15:
        return 0

    root = _find_package()
    if root:
        sys.path.insert(0, root)
    try:
        from nativeprompt.explain import build_report
        rep = build_report(prompt)
    except Exception:
        return 0

    if rep.get("error") or not rep.get("target", {}).get("family"):
        return 0
    findings = [f for f in rep.get("findings", []) if not f.get("always")]
    if not findings:
        return 0  # промпт и так по правилам — молчим

    t = rep["target"]
    lines = [
        "[nativeprompt] Ваш промпт можно улучшить под %s (%s):"
        % (t.get("cli"), t.get("model_id") or t.get("family"))
    ]
    for f in findings[:6]:
        lines.append("- %s — %s" % (f["title"], f["source"]))
    lines.append("\nУлучшенная версия промпта:\n%s" % rep["improved"])
    h = rep.get("harness")
    if h:
        lines.append("\nКак запускать: %s — %s" % (h["command"], h["title"]))
    lines.append("\n(Действуй по улучшенной версии; недостающее в ‹…› уточни у пользователя.)")

    out = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "\n".join(lines),
        }
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
