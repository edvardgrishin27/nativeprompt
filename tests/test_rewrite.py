"""Детерминированная перепись + мета-промт + границы (не выдумываем)."""

from nativeprompt.analyze import analyze
from nativeprompt.harness import recommend_harness
from nativeprompt.rewrite import rewrite, build_metaprompt

CLAUDE = {"family": "claude", "generation": "opus-5", "model_id": "claude-opus-5"}
OPENAI = {"family": "openai", "generation": "gpt-5.6", "model_id": "gpt-5.6"}


def _improve(prompt, target):
    findings = analyze(prompt, target)
    return rewrite(prompt, target, findings)


def test_strip_cot_openai():
    r = _improve("Реализуй парсер, думай пошагово.", OPENAI)
    assert "пошагово" not in r["improved"].lower()
    assert "codex-no-forced-cot" in r["applied"]


def test_cot_kept_for_claude():
    # у Claude CoT допустим — не должны его вырезать
    r = _improve("Реализуй парсер в @a.py, думай пошагово, прогони тесты.", CLAUDE)
    assert "пошагово" in r["improved"].lower()


def test_soften_caps():
    r = _improve("ОБЯЗАТЕЛЬНО добавь тест в @a.py и прогони pytest.", CLAUDE)
    assert "ОБЯЗАТЕЛЬНО" not in r["improved"]


def test_remove_verification_opus5():
    r = _improve("Почини @a.py, прогони тесты и обязательно перепроверь себя.", CLAUDE)
    assert "перепроверь" not in r["improved"].lower()
    assert "opus5-remove-verification" in r["applied"]


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
