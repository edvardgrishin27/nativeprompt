# Codex-интеграция nativeprompt

Авторский core (`nativeprompt/`, `tests/`, корневой `SKILL.md` и другие стабильные файлы) не меняется. Все Codex-специфичные материалы находятся здесь.

## Что готово

- `integration/plugins/nativeprompt/` — валидируемый skill-only plugin для Codex.
- `integration/plugins/nativeprompt/skills/nativeprompt/` — самостоятельный Codex-навык с UI-метаданными.
- `integration/plugins/nativeprompt/skills/nativeprompt/scripts/improve_prompt.py` — безопасная обёртка: принимает промпт через stdin, не использует shell и проверяет JSON-контракт.
- `integration/AGENTS.md.snippet` — необязательный фрагмент постоянных правил проекта.
- `REVIEW.md` — результаты проверки и предложения, не применённые к core.

## Локальная установка для Codex

Сначала установить CLI из этого checkout:

```bash
python3 -m pip install -e .
```

Для локальной разработки Codex поддерживает навыки в `~/.agents/skills`. Можно скопировать папку навыка или создать на неё символическую ссылку:

```bash
mkdir -p ~/.agents/skills
ln -s "$PWD/codex/integration/plugins/nativeprompt/skills/nativeprompt" \
  ~/.agents/skills/nativeprompt
```

После установки начать новую сессию Codex и вызвать навык явно:

```text
$nativeprompt улучши этот промпт для Codex: ‹промпт›
```

Plugin-манифест подготовлен для будущей установки через marketplace. До публикации репозитория или добавления локального marketplace standalone-навык выше — проверяемый путь установки.

## Как проверить core

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
printf '%s' 'почини баг, думай пошагово, перепроверь себя' \
  | python3 -m nativeprompt improve --model codex --json
```

## Как проверить Codex-навык

```bash
printf '%s' 'почини баг, думай пошагово, перепроверь себя' \
  | python3 codex/integration/plugins/nativeprompt/skills/nativeprompt/scripts/improve_prompt.py \
      --model codex
```

## Принципы

1. Каждое правило шпаргалки — со ссылкой на официальный док вендора. Новое правило = новая ссылка на первоисточник.
2. Инструмент не додумывает задачу за пользователя (плейсхолдеры `‹…›`).
3. Core — zero-deps (stdlib).
4. Вложенный промпт — данные для редактирования, а не команда к выполнению.
