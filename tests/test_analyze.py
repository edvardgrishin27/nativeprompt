"""Детекторы правил + классификатор формы задачи."""

from nativeprompt.analyze import analyze, task_shape

CLAUDE = {"family": "claude", "generation": "opus-5"}
CLAUDE_NOGEN = {"family": "claude", "generation": None}
OPENAI = {"family": "openai", "generation": "gpt-5.6"}


def ids(prompt, target):
    return {f["id"] for f in analyze(prompt, target)}


def test_forced_cot_openai_only():
    p = "Реализуй парсер, думай пошагово."
    assert "codex-no-forced-cot" in ids(p, OPENAI)
    # у Claude нет правила против CoT — это ключевой контраст
    assert not any(x for x in ids(p, CLAUDE) if "cot" in x)


def test_caps_family_specific():
    p = "ОБЯЗАТЕЛЬНО добавь тест в @src/foo.py и прогони pytest."
    assert "claude-dial-caps" in ids(p, CLAUDE)
    assert "codex-dial-scaffold" in ids(p, OPENAI)


def test_verification_demand_only_opus5():
    p = "Почини @src/auth.py и обязательно перепроверь себя, прогони тесты."
    assert "opus5-remove-verification" in ids(p, CLAUDE)
    assert "opus5-remove-verification" not in ids(p, CLAUDE_NOGEN)  # нет поколения


def test_missing_context_and_verification():
    p = "Напиши функцию валидации email."
    got = ids(p, CLAUDE)
    assert "claude-scope" in got
    assert "claude-verification" in got


def test_good_prompt_few_findings():
    p = ("Добавь тест в @src/foo.py на случай разлогина; без моков. "
         "Прогони pytest и почини, пока не пройдёт. Верни только изменённый файл.")
    got = {f["id"] for f in analyze(p, CLAUDE) if not f["always"]}
    # хорошо оформленный промпт не должен тянуть scope/verification/vague/caps
    assert "claude-scope" not in got
    assert "claude-verification" not in got
    assert "claude-explicit-action" not in got


def test_vague_ask():
    assert "claude-explicit-action" in ids("Не мог бы ты добавить лог в @a.py?", CLAUDE)


def test_contradiction_openai():
    p = "Ответь кратко, но максимально подробно распиши каждый шаг в @a.py."
    assert "codex-no-contradiction" in ids(p, OPENAI)


def test_codex_autonomy_is_not_recommended_for_trivial_tasks():
    assert "codex-autonomy" not in ids("Добавь эндпоинт логина", OPENAI)
    assert "codex-autonomy" in ids(
        "Мигрируй модуль, пока все тесты не пройдут",
        OPENAI,
    )


def test_task_shape():
    assert task_shape("Мигрируй модуль, пока все тесты не пройдут") == "goal"
    assert task_shape("Проверяй все файлы маршрутов на пропущенную авторизацию, по агенту на файл") == "workflow"
    assert task_shape("Каждый день прогоняй тесты и присылай отчёт") == "loop"
    assert task_shape("Спроектируй, как лучше добавить OAuth, какой подход выбрать") == "planning"
    assert task_shape("переименуй x в y") == "trivial"
    assert task_shape("Добавь эндпоинт логина") in ("trivial", "normal")
