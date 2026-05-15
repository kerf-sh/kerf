"""Manifest parse + validation + selection. Pure, no network, no I/O
beyond reading the bundled committed manifest.
"""
import pytest

from kerf_parts.manifest import (
    ManifestError,
    Source,
    load_manifest,
    parse_manifest,
    select_sources,
)


def test_bundled_manifest_parses():
    sources = load_manifest()
    names = {s.name for s in sources}
    # Every seeded source from the spec must be present.
    assert {
        "kicad-symbols",
        "kicad-footprints",
        "kicad-packages3D",
        "bolts",
        "freecad-library",
    } <= names


def test_bundled_manifest_is_pinned_and_typed():
    for s in load_manifest():
        assert s.ref, f"{s.name} must be pinned to a ref"
        assert s.git_url.startswith("https://"), s.name
        assert s.adapter, s.name
        assert isinstance(s.heavy, bool)
    by_name = {s.name: s for s in load_manifest()}
    # packages3D is the only heavy source.
    assert by_name["kicad-packages3D"].heavy is True
    assert by_name["kicad-symbols"].heavy is False


def test_parse_rejects_missing_fields():
    with pytest.raises(ManifestError, match="missing required"):
        parse_manifest(
            """
            [[source]]
            name = "x"
            git_url = "https://example.com/x.git"
            """
        )


def test_parse_rejects_no_sources():
    with pytest.raises(ManifestError, match="no \\[\\[source\\]\\]"):
        parse_manifest('manifest_version = 1\n')


def test_parse_rejects_duplicate_names():
    toml = """
    [[source]]
    name = "dup"
    git_url = "https://e/x.git"
    ref = "1"
    license = "MIT"
    format = "f"
    adapter = "kicad"

    [[source]]
    name = "dup"
    git_url = "https://e/y.git"
    ref = "1"
    license = "MIT"
    format = "f"
    adapter = "kicad"
    """
    with pytest.raises(ManifestError, match="duplicate"):
        parse_manifest(toml)


def test_parse_rejects_non_http_url():
    toml = """
    [[source]]
    name = "x"
    git_url = "git@github.com:foo/bar.git"
    ref = "1"
    license = "MIT"
    format = "f"
    adapter = "kicad"
    """
    with pytest.raises(ManifestError, match="http"):
        parse_manifest(toml)


def _sources():
    return [
        Source("a", "https://e/a.git", "1", "MIT", "f", "kicad", heavy=False),
        Source("b", "https://e/b.git", "2", "MIT", "f", "bolts", heavy=False),
        Source("big", "https://e/big.git", "9", "MIT", "f", "kicad3d", heavy=True),
    ]


def test_select_skips_heavy_by_default():
    out = {s.name for s in select_sources(_sources())}
    assert out == {"a", "b"}


def test_select_heavy_included_with_flag():
    out = {s.name for s in select_sources(_sources(), include_heavy=True)}
    assert out == {"a", "b", "big"}


def test_select_only_subset():
    out = [s.name for s in select_sources(_sources(), only=["a"])]
    assert out == ["a"]


def test_select_only_can_force_heavy():
    # naming a heavy source explicitly pulls it even without include_heavy
    out = [s.name for s in select_sources(_sources(), only=["big"])]
    assert out == ["big"]


def test_select_ref_override():
    out = select_sources(_sources(), ref_overrides={"a": "99"})
    a = next(s for s in out if s.name == "a")
    assert a.ref == "99"


def test_select_unknown_only_raises():
    with pytest.raises(ManifestError, match="unknown source"):
        select_sources(_sources(), only=["nope"])


def test_select_unknown_ref_override_raises():
    with pytest.raises(ManifestError, match="unknown source"):
        select_sources(_sources(), ref_overrides={"nope": "1"})
