"""Детерминированная перепись + мета-промпт + границы (не выдумываем)."""

from nativeprompt.analyze import analyze
from nativeprompt.harness import recommend_harness
from nativeprompt.rewrite import rewrite, build_metaprompt

CLAUDE = {"family": "claude", "generation": "opus-5", "model_id": "claude-opus-5"}
OPENAI = {"family": "openai", "generation": "gpt-5.6", "model_id": "gpt-5.6"}


def _improve(prompt, target):
    findings = analyze(prompt, target)
    return rewrite(prompt, target, findings)


def test_forced_cot_warns_but_keeps_text_for_openai():
    """`codex-no-forced-cot` теперь только предупреждает: находка есть, текст цел.

    Отличить навязанную модели цепочку рассуждений от заказанного формата
    ответа по форме нельзя — та же причина, что увела `opus5-remove-
    verification` в предупреждение (см. rules/openai.json).
    """
    findings = analyze("Реализуй парсер, думай пошагово.", OPENAI)
    r = rewrite("Реализуй парсер, думай пошагово.", OPENAI, findings)
    assert "codex-no-forced-cot" in {f["id"] for f in findings}
    assert "codex-no-forced-cot" not in r["applied"]
    assert "пошагово" in r["improved"].lower()


def test_cot_kept_for_claude():
    # у Claude CoT допустим — не должны его вырезать
    r = _improve("Реализуй парсер в @a.py, думай пошагово, прогони тесты.", CLAUDE)
    assert "пошагово" in r["improved"].lower()


def test_soften_caps():
    r = _improve("ОБЯЗАТЕЛЬНО добавь тест в @a.py и прогони pytest.", CLAUDE)
    assert "ОБЯЗАТЕЛЬНО" not in r["improved"]


def test_verification_demand_показывается_но_не_вырезается():
    """Правило вендора верное, но вырезать текст инструмент больше не берётся.

    Удаление было единственной переписью, уничтожающей содержимое, и трижды
    подряд уничтожало не то: требование к результату, среднее звено условия,
    целое предложение с реальным шагом задачи. Отличить вежливый оборот от
    части задания по форме нельзя — поэтому находку показываем, режет человек.
    """
    from nativeprompt.analyze import analyze

    p = "Почини @a.py, прогони тесты и обязательно перепроверь себя."
    r = _improve(p, CLAUDE)
    assert "перепроверь себя" in r["improved"], "инструмент снова режет текст сам"
    ids = {f["id"] for f in analyze(p, CLAUDE)}
    assert "opus5-remove-verification" in ids, "правило перестало предупреждать"


def test_placeholder_when_missing_context():
    r = _improve("Напиши функцию валидации email.", CLAUDE)
    assert "‹" in r["improved"]  # плейсхолдер, а не выдуманный путь


def test_no_invention_of_files():
    # инструмент не должен придумывать имена файлов
    r = _improve("Напиши функцию валидации email.", CLAUDE)
    assert "src/foo" not in r["improved"]  # пример из правила не должен протечь как факт


def test_xml_wrap_for_multipart_claude():
    long_prompt = ("Вот контекст и пример. " * 40) + " Реализуй по описанию."
    r = _improve(long_prompt, CLAUDE)
    assert "<instructions>" in r["improved"]


def test_metaprompt_contains_rules_and_prompt():
    p = "Не мог бы ты добавить лог."
    findings = analyze(p, CLAUDE)
    harness = recommend_harness(p, CLAUDE)
    mp = build_metaprompt(p, CLAUDE, findings, harness)
    assert "PROMPT:" in mp
    assert "claude-opus-5" in mp
    assert "НИЧЕГО не додумывай" in mp
    assert findings
    assert all(f["source"] in mp for f in findings)
    assert harness["source"] in mp
