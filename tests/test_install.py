"""`install` ставит навык туда, где его видят обе среды.

Живой случай: человек сделал `pipx install nativeprompt`, навык не появился,
и в чате он получил «такого инструмента не существует». Причина была не в нём:
SKILL.md лежал только в репозитории, в колесо попадали одни `rules/*.json`,
и копировать навык после установки пакета было физически неоткуда.

Каталог ~/.claude/skills читают и терминал, и десктопное приложение, поэтому
установка одна на обе среды.
"""

import glob
import io
import os
import subprocess
import sys
import zipfile

import pytest

КОРЕНЬ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def запустить(*args, **kw):
    return subprocess.run([sys.executable, "-m", "nativeprompt", *args],
                          capture_output=True, text=True, cwd=КОРЕНЬ, **kw)


def test_навык_ставится_в_указанный_каталог(tmp_path):
    r = запустить("install", "--dir", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "nativeprompt" / "SKILL.md").exists()


def test_поставленный_навык_совпадает_с_исходником(tmp_path):
    """Иначе можно поставить пустышку и не заметить."""
    запустить("install", "--dir", str(tmp_path))
    поставлен = (tmp_path / "nativeprompt" / "SKILL.md").read_text(encoding="utf-8")
    assert поставлен.startswith("---"), "у навыка пропал frontmatter"
    assert "name: nativeprompt" in поставлен
    assert len(поставлен) > 1000, "навык подозрительно короткий"


def test_повтор_без_форс_не_затирает_молча(tmp_path):
    """Человек мог править навык под себя: молча затирать нельзя."""
    запустить("install", "--dir", str(tmp_path))
    (tmp_path / "nativeprompt" / "SKILL.md").write_text("моя правка", encoding="utf-8")
    r = запустить("install", "--dir", str(tmp_path))
    assert r.returncode == 1
    assert "--force" in r.stderr
    assert (tmp_path / "nativeprompt" / "SKILL.md").read_text(encoding="utf-8") == "моя правка"


def test_форс_перезаписывает(tmp_path):
    запустить("install", "--dir", str(tmp_path))
    (tmp_path / "nativeprompt" / "SKILL.md").write_text("старое", encoding="utf-8")
    r = запустить("install", "--dir", str(tmp_path), "--force")
    assert r.returncode == 0
    assert "name: nativeprompt" in (tmp_path / "nativeprompt" / "SKILL.md").read_text(encoding="utf-8")


def test_подсказка_называет_обе_среды_и_границу_применения(tmp_path):
    """Две ошибки, на которых спотыкались, обязаны быть закрыты текстом вывода.

    Первая: искали слэш-команду. Второй: просили написать поздравление, хотя
    инструмент улучшает промпты, а не выполняет задачи.
    """
    вывод = запустить("install", "--dir", str(tmp_path)).stdout
    assert "приложении" in вывод, "не сказано, что работает и в приложении"
    assert "слэш" in вывод, "не сказано, что слэш-команды нет"
    assert "ПРОМПТЫ" in вывод, "не названа граница применения"


def test_skill_md_объявлен_в_package_data_и_файл_на_месте():
    """Корень той самой поломки: навык обязан ехать В ПАКЕТЕ.

    Раньше в package-data стояли только `rules/*.json`, SKILL.md жил в корне
    репозитория, и после `pipx install` копировать навык было неоткуда.
    Проверяется не текст в pyproject сам по себе, а то, что каждый объявленный
    путь указывает на существующий файл: объявление без файла так же бесполезно,
    как файл без объявления.
    """
    import re

    манифест = open(os.path.join(КОРЕНЬ, "pyproject.toml"), encoding="utf-8").read()
    m = re.search(r"(?ms)^nativeprompt = \[(.*?)\]", манифест)
    assert m, "в package-data не нашлась строка для пакета nativeprompt"
    шаблоны = re.findall(r'"([^"]+)"', m.group(1))
    assert any("SKILL.md" in ш for ш in шаблоны), (
        "SKILL.md не объявлен в package-data, install после pipx будет пустым: %s" % шаблоны)

    for ш in шаблоны:
        найдено = glob.glob(os.path.join(КОРЕНЬ, "nativeprompt", ш))
        assert найдено, "шаблон %r из package-data не находит ни одного файла" % ш


def test_навык_в_пакете_не_разъехался_с_корневым():
    """Копия в пакете и файл в корне репозитория обязаны совпадать.

    Иначе правишь навык в корне, а людям после установки едет старый.
    """
    в_пакете = os.path.join(КОРЕНЬ, "nativeprompt", "assets", "skill", "SKILL.md")
    в_корне = os.path.join(КОРЕНЬ, "SKILL.md")
    if not os.path.exists(в_корне):
        pytest.skip("корневого SKILL.md нет")
    a = open(в_пакете, encoding="utf-8").read()
    b = open(в_корне, encoding="utf-8").read()
    assert a == b, "SKILL.md в пакете разошёлся с корневым"


# ═══════════════════════════════════════════════════════════════════════
# Второй акт той же болезни: pipx-установка не самодостаточна.
# Первый был про навык (SKILL.md вне пакета). Этот про хук: человек ставит
# `pipx install nativeprompt`, прописывает хук строкой из README, и хук молчит.
# Причина: pipx кладёт пакет в отдельное окружение, а `python3` из инструкции
# его не видит. `import nativeprompt` падает, каталога репозитория рядом нет,
# и хук уходит в тихий ноль — ровно так, как ему велено при любой ошибке.
# Пользователь видит ничего и не понимает, почему.
# ═══════════════════════════════════════════════════════════════════════
def _положить_пакет(корень, имя_вэнва="nativeprompt"):
    """Собрать правдоподобный venv с пакетом внутри и вернуть его site-packages."""
    import sys as _s
    вэнв = os.path.join(корень, "venvs", имя_вэнва)
    site = os.path.join(вэнв, "lib", "python%d.%d" % _s.version_info[:2], "site-packages")
    os.makedirs(os.path.join(site, "nativeprompt"))
    io.open(os.path.join(site, "nativeprompt", "__init__.py"), "w").write("")
    os.makedirs(os.path.join(вэнв, "bin"))
    бинарь = os.path.join(вэнв, "bin", "nativeprompt")
    io.open(бинарь, "w").write("#!/bin/sh\n")
    os.chmod(бинарь, 0o755)
    return site, бинарь


def test_хук_находит_пакет_поставленный_через_pipx(tmp_path, monkeypatch):
    """Живой отзыв: «поставил хук по раздатке, а он молчал всегда».

    Хук обязан найти пакет в чужом окружении сам. Заставлять человека вписывать
    путь вида ~/Library/Application Support/pipx/venvs/... значит переложить на
    него разницу между macOS, Linux и Windows.
    """
    import importlib.util
    корень = str(tmp_path / "pipx")
    site, бинарь = _положить_пакет(корень)
    monkeypatch.setenv("PIPX_HOME", корень)
    monkeypatch.delenv("NATIVEPROMPT_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)

    spec = importlib.util.spec_from_file_location(
        "_хук", os.path.join(КОРЕНЬ, "hooks", "nativeprompt_hook.py"))
    хук = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(хук)

    # эмулируем чужое окружение: пакет НЕ импортируется, репозитория рядом нет
    monkeypatch.setattr(хук, "_РЕПОЗИТОРИЙ_РЯДОМ", False, raising=False)
    найдено = хук._искать_в_чужих_окружениях()
    assert найдено == site, "pipx-окружение не найдено: %r вместо %r" % (найдено, site)


def test_хук_находит_пакет_поставленный_через_uv_tool(tmp_path, monkeypatch):
    """uv tool install кладёт иначе, чем pipx, и он всё популярнее."""
    import importlib.util
    корень = str(tmp_path / "uv" / "tools")
    вэнв = os.path.join(корень, "nativeprompt")
    import sys as _s
    site = os.path.join(вэнв, "lib", "python%d.%d" % _s.version_info[:2], "site-packages")
    os.makedirs(os.path.join(site, "nativeprompt"))
    io.open(os.path.join(site, "nativeprompt", "__init__.py"), "w").write("")
    monkeypatch.setenv("UV_TOOL_DIR", корень)
    monkeypatch.delenv("PIPX_HOME", raising=False)

    spec = importlib.util.spec_from_file_location(
        "_хук2", os.path.join(КОРЕНЬ, "hooks", "nativeprompt_hook.py"))
    хук = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(хук)
    assert хук._искать_в_чужих_окружениях() == site


def test_хук_говорит_вслух_когда_пакет_не_найден(tmp_path, monkeypatch, capsys):
    """Тихий ноль — правильное поведение при ЛЮБОЙ ошибке работы, но не тогда,
    когда пакета просто нет. Молчание в этом случае неотличимо от «промпт хороший».
    """
    import importlib.util
    monkeypatch.setenv("PIPX_HOME", str(tmp_path / "пусто"))
    monkeypatch.setenv("UV_TOOL_DIR", str(tmp_path / "пусто2"))
    monkeypatch.delenv("NATIVEPROMPT_HOME", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    spec = importlib.util.spec_from_file_location(
        "_хук3", os.path.join(КОРЕНЬ, "hooks", "nativeprompt_hook.py"))
    хук = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(хук)
    хук._пожаловаться_один_раз()
    err = capsys.readouterr().err
    assert "nativeprompt" in err and "не найден" in err, "хук молчит о ненайденном пакете: %r" % err
