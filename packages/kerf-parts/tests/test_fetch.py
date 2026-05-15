"""Fetcher: clone-decision logic + fetch_source flow with a fully mocked
git runner and a tmp filesystem. NO network, NO real git.
"""
import subprocess

import pytest

from kerf_parts.fetch import (
    Action,
    CloneState,
    FetchResult,
    decide_action,
    fetch_source,
    inspect_cache,
)
from kerf_parts.manifest import Source


# ---- pure decision logic -------------------------------------------------

def test_decide_clone_when_no_cache():
    st = CloneState(cache_exists=False, is_git_repo=False, current_ref=None)
    assert decide_action(st, "1.0") is Action.CLONE


def test_decide_clone_when_dir_not_git():
    st = CloneState(cache_exists=True, is_git_repo=False, current_ref=None)
    assert decide_action(st, "1.0") is Action.CLONE


def test_decide_skip_when_ref_matches():
    st = CloneState(cache_exists=True, is_git_repo=True, current_ref="1.0")
    assert decide_action(st, "1.0") is Action.SKIP


def test_decide_refresh_when_ref_differs():
    st = CloneState(cache_exists=True, is_git_repo=True, current_ref="0.9")
    assert decide_action(st, "1.0") is Action.REFRESH


def test_decide_refresh_when_ref_unknown():
    st = CloneState(cache_exists=True, is_git_repo=True, current_ref=None)
    assert decide_action(st, "1.0") is Action.REFRESH


# ---- inspect_cache against a tmp filesystem ------------------------------

def test_inspect_cache_missing(tmp_path):
    st = inspect_cache(tmp_path / "nope")
    assert st == CloneState(False, False, None)


def test_inspect_cache_not_git(tmp_path):
    d = tmp_path / "x"
    d.mkdir()
    st = inspect_cache(d)
    assert st.cache_exists and not st.is_git_repo


def test_inspect_cache_git_resolves_ref(tmp_path):
    d = tmp_path / "x"
    (d / ".git").mkdir(parents=True)

    def fake_runner(args, cwd=None):
        if args[:1] == ["describe"]:
            return subprocess.CompletedProcess(args, 0, stdout="9.0.9\n", stderr="")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    st = inspect_cache(d, runner=fake_runner)
    assert st.is_git_repo and st.current_ref == "9.0.9"


# ---- fetch_source flow with mocked runner --------------------------------

SRC = Source("kicad-symbols", "https://e/k.git", "9.0.9", "CC", "kicad-sym", "kicad")


def test_fetch_skips_when_up_to_date(tmp_path):
    dest = tmp_path / "kicad-symbols"
    (dest / ".git").mkdir(parents=True)

    def runner(args, cwd=None):
        if args[:1] == ["describe"]:
            return subprocess.CompletedProcess(args, 0, stdout="9.0.9\n", stderr="")
        raise AssertionError(f"unexpected git call: {args}")

    res = fetch_source(SRC, tmp_path, runner=runner, log=lambda *_: None)
    assert res.action is Action.SKIP and res.ok


def test_fetch_clones_when_absent(tmp_path):
    calls = []

    def runner(args, cwd=None):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    res = fetch_source(SRC, tmp_path, runner=runner, log=lambda *_: None)
    assert res.action is Action.CLONE and res.ok
    clone = calls[0]
    assert clone[0] == "clone"
    assert "--depth" in clone and "1" in clone
    assert "--branch" in clone and "9.0.9" in clone
    assert SRC.git_url in clone


def test_fetch_clone_failure_is_graceful(tmp_path):
    def runner(args, cwd=None):
        return subprocess.CompletedProcess(
            args, 128, stdout="", stderr="fatal: repository not found"
        )

    res = fetch_source(SRC, tmp_path, runner=runner, log=lambda *_: None)
    assert isinstance(res, FetchResult)
    assert res.action is Action.CLONE
    assert res.ok is False
    assert "not found" in res.message


def test_fetch_refresh_when_wrong_ref(tmp_path):
    dest = tmp_path / "kicad-symbols"
    (dest / ".git").mkdir(parents=True)
    seq = []

    def runner(args, cwd=None):
        seq.append(args[0])
        if args[:1] == ["describe"]:
            return subprocess.CompletedProcess(args, 0, stdout="9.0.8\n", stderr="")
        if args[:1] == ["rev-parse"]:
            return subprocess.CompletedProcess(args, 0, stdout="9.0.8\n", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    res = fetch_source(SRC, tmp_path, runner=runner, log=lambda *_: None)
    assert res.action is Action.REFRESH and res.ok
    assert "fetch" in seq and "checkout" in seq
