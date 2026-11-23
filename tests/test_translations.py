"""Every translation has the keys and the placeholders of en.json."""

import json
import pathlib
import re

import pytest

DIR = pathlib.Path(__file__).parent.parent / "custom_components/triki/translations"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def flat(d: dict, prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in d.items():
        path = f"{prefix}.{key}" if prefix else key
        out |= flat(value, path) if isinstance(value, dict) else {path: value}
    return out


EN = flat(json.loads((DIR / "en.json").read_text(encoding="utf-8")))
OTHERS = sorted(p.name for p in DIR.glob("*.json") if p.name != "en.json")


def test_the_languages_are_there() -> None:
    assert OTHERS == ["pl.json", "ru.json"]


@pytest.mark.parametrize("name", OTHERS)
def test_same_keys_and_placeholders(name: str) -> None:
    other = flat(json.loads((DIR / name).read_text(encoding="utf-8")))
    assert sorted(other) == sorted(EN)
    for key, text in EN.items():
        assert set(PLACEHOLDER.findall(other[key])) == set(PLACEHOLDER.findall(text)), key
        assert other[key].strip(), key
