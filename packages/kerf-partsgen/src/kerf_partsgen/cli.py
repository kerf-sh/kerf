"""kerf-partsgen CLI.

    kerf-partsgen list                          # show wishlist + state
    kerf-partsgen author  <family_id>           # LLM (needs ANTHROPIC_API_KEY)
    kerf-partsgen enumerate [--only <id>]       # ZERO tokens → .parts-out/
    kerf-partsgen seed [--out <dir>]            # promote [x] families

Run from anywhere inside the repo (the repo root is auto-detected by walking
up to the dir that holds ``docs/parts/wishlist``); override with --repo-root.
"""

from __future__ import annotations

import argparse
import os
import sys

from kerf_partsgen import kernel
from kerf_partsgen.enumerate import enumerate_wishlist, summarize
from kerf_partsgen.wishlist import parse_wishlist_file


def _find_repo_root(start: str | None = None) -> str:
    cur = os.path.abspath(start or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cur, "docs", "parts", "wishlist")):
            return cur
        if os.path.isdir(os.path.join(cur, ".git")) or os.path.isfile(
            os.path.join(cur, ".git")
        ):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return os.path.abspath(start or os.getcwd())
        cur = parent


def _wishlist_path(repo_root: str, domain: str) -> str:
    return os.path.join(repo_root, "docs", "parts", "wishlist", f"{domain}.md")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kerf-partsgen")
    p.add_argument("--repo-root", default=None)
    p.add_argument("--domain", default="mechanical")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="show wishlist families + state")

    ap = sub.add_parser("author", help="author one family with the LLM")
    ap.add_argument("family_id")
    ap.add_argument("--label", default=None, help="override family label")
    ap.add_argument("--standard", default=None, help="override standard ref")

    ep = sub.add_parser("enumerate", help="deterministic, zero-token build")
    ep.add_argument("--only", default=None, help="single family_id")

    sp = sub.add_parser("seed", help="promote [x]-approved families")
    sp.add_argument("--out", default=None, help="PartDoc output dir")

    args = p.parse_args(argv)
    repo_root = args.repo_root or _find_repo_root()
    wl_path = _wishlist_path(repo_root, args.domain)

    if args.cmd == "list":
        if not os.path.isfile(wl_path):
            print(f"no wishlist at {wl_path}", file=sys.stderr)
            return 2
        rows = parse_wishlist_file(wl_path)
        print(f"wishlist {wl_path}  ({len(rows)} families)")
        print(f"kernel backend: {kernel.KERNEL_BACKEND}")
        for r in rows:
            mark = "[x] approved " if r.approved else "[ ] pending  "
            print(f"  {mark} {r.family_id:<34} {r.name}")
        return 0

    if args.cmd == "enumerate":
        results = enumerate_wishlist(
            repo_root, domain=args.domain, only=args.only
        )
        print(summarize(results))
        print(f"\nartifacts under: {os.path.join(repo_root, '.parts-out')}")
        print("This wrote NO tracked file. Review .parts-out/, then tick "
              "[x] in the wishlist by hand and commit that one line.")
        any_fail = any(fr.failed or fr.error for fr in results)
        return 1 if any_fail else 0

    if args.cmd == "author":
        from kerf_partsgen.author import author_family

        rows = parse_wishlist_file(wl_path) if os.path.isfile(wl_path) else []
        match = next((r for r in rows if r.family_id == args.family_id), None)
        label = args.label or (match.name if match else args.family_id)
        standard = args.standard or (
            match.name if match else args.family_id
        )
        outcome = author_family(
            args.family_id, label, standard, repo_root, domain=args.domain
        )
        print(
            f"author {outcome.family_id}: {outcome.status} "
            f"({outcome.attempts} LLM call(s)) — {outcome.detail}"
        )
        if outcome.status == "AUTHORED":
            print(f"wrote {outcome.generator_path}")
            print("Review the generator + table in the diff, then run "
                  "`kerf-partsgen enumerate` (zero tokens).")
            return 0
        return 1

    if args.cmd == "seed":
        from kerf_partsgen.seed import seed_wishlist

        manifest = seed_wishlist(
            repo_root, domain=args.domain, out_dir=args.out
        )
        print(
            f"seed: {manifest['families']} approved families → "
            f"{len(manifest['written'])} PartDoc files in "
            f"{manifest['out_dir']} ({manifest['skipped_fail']} variants "
            f"skipped: gate FAIL)"
        )
        for w in manifest["written"]:
            print(f"  + {w}")
        print("Review + `git add` these PartDoc files, then run Kerf's own "
              "publishers seeder to load them.")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
