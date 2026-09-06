# Codex-интеграция nativeprompt

Авторский core (`nativeprompt/`, `tests/`, корневой `SKILL.md` и другие стабильные файлы) не меняется. Все Codex-специфичные материалы находятся здесь.

## Текущий безопасный маршрут

Для ChatGPT/Codex/OpenAI используется защитный адаптер. Он не доверяет полям
`improved` и `metaprompt` из upstream `0.1.0`, а строит пользовательский отчёт
из исходного промпта и двух текущих официальных источников OpenAI:

- https://learn.chatgpt.com/docs/prompting

- https://developers.openai.com/api/docs/guides/latest-model

Адаптер сохраняет отрицания, пути, URL, числа, формат ответа и границы
полномочий. Запросы plan, review, audit, explain и diagnose не получают
разрешение на реализацию. Вход сериализуется в JSON, поэтому `>>>` не может
закрыть блок данных. Если проверка смысла не проходит, возвращается исходный
промпт.

Правила хранятся локально как проверенный срез официальных рекомендаций, а не
скачиваются заново при каждом запуске. В JSON фиксируются владелец `OpenAI`,
режим `official_only` и дата последней живой сверки. Claude и другие семейства
этот адаптер не изменяет, их запросы передаются upstream.

`~/.codex/config.toml` используется только для определения активной модели.
Персональные инструкции, permissions, hooks и `AGENTS.md` не участвуют в
переписи промпта. Если локальный срез старше 30 дней или появилась новая модель,
skill требует перепроверить только официальные страницы OpenAI, не передавая
туда пользовательский промпт.

## Что готово

- `integration/plugins/nativeprompt/` — валидируемый skill-only plugin для Codex.
- `integration/plugins/nativeprompt/skills/nativeprompt/` — самостоятельный Codex-навык с UI-метаданными.
- `integration/plugins/nativeprompt/skills/nativeprompt/scripts/improve_prompt.py`: безопасная обёртка принимает промпт через stdin, не использует shell, проверяет JSON-контракт и применяет смысловой guard.
- `integration/plugins/nativeprompt/skills/nativeprompt/scripts/safe_prompt.py`: актуальные OpenAI-правила и инварианты сохранения смысла.
- `integration/bin/nativeprompt`: совместимый launcher безопасно обрабатывает `improve` для OpenAI, остальные команды передаёт upstream.
- `tests/test_safe_prompt.py`: regression-набор для отрицаний, полномочий, формата, `>>>`, launcher, U+2014 и идемпотентности.
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

Для безопасного глобального CLI сначала сохранить upstream под отдельным
именем, затем направить `nativeprompt` на launcher:

```bash
ln -s ~/.local/share/uv/tools/nativeprompt/bin/nativeprompt \
  ~/.local/bin/nativeprompt-upstream
ln -s "$PWD/codex/integration/bin/nativeprompt" ~/.local/bin/nativeprompt
```

Plugin-манифест подготовлен для будущей установки через marketplace. До публикации репозитория или добавления локального marketplace standalone-навык выше — проверяемый путь установки.

## Как проверить core

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider
printf '%s' 'почини баг, думай пошагово, перепроверь себя' \
  | python3 -m nativeprompt improve --model codex --json
```

Полный гейт с Codex regression-набором:

```bash
python3 -m pytest -q -p no:cacheprovider tests codex/tests
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
