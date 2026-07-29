"""Самообновление: манифест + рендер (без сети)."""

from nativeprompt import catalog
from nativeprompt import update as up


def test_manifest_urls():
    urls = up._all_urls()
    assert urls
    fams = {fam for fam, _ in urls}
    assert {"claude", "openai"} <= fams
    for _fam, u in urls:
        assert u.startswith("https://")


def test_render_synthetic():
    fake = {
        "results": [
            {"family": "claude", "url": "https://x/a.md", "status": "changed"},
            {"family": "openai", "url": "https://x/b.md", "status": "unchanged"},
            {"family": "claude", "url": "https://x/c.md", "status": "unreachable", "detail": "timeout"},
        ],
        "summary": {"changed": 1, "new": 0, "unchanged": 1, "unreachable": 1,
                    "total": 3, "action_needed": True, "wrote_snapshot": False},
    }
    text = up.render_update(fake)
    assert "изменилось" in text
    assert "Офиц. доки изменились" in text


def test_sources_loadable():
    src = catalog.load_sources()
    assert src["families"]["claude"]["index"].endswith("llms.txt")
