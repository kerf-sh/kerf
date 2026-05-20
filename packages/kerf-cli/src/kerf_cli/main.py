"""kerf — mode-agnostic CLI entry point.

Subcommands
-----------
kerf login       Store API token + server URL in ~/.config/kerf/credentials.
kerf serve       Self-host path: requires Postgres.  Fails fast if DB is missing
                 or unreachable.
kerf hydrate     Resolve LFS pointer stubs → real bytes from Kerf cloud storage.
kerf pull-blobs  Alias for kerf hydrate (plain-git-clone context).
kerf sync        Two-way folder mirror between a local directory and a cloud
                 project (T-127).
kerf export      Materialise a project as a plain file tree on disk (T-322).
kerf import      Re-create a project from a materialised export directory (T-322).
"""

from __future__ import annotations

import argparse
import sys


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

def _cmd_login(args: argparse.Namespace) -> int:
    from kerf_cli.credentials import save_credentials, _DEFAULT_API_URL  # noqa: PLC0415

    api_url = (args.api_url or _DEFAULT_API_URL).rstrip("/")
    api_token = args.token

    if not api_token:
        # Interactive prompt when token not supplied on the command line
        try:
            api_token = input(f"API token (from {api_url}/settings): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.", file=sys.stderr)
            return 1

    if not api_token:
        print("Error: API token must not be empty.", file=sys.stderr)
        return 1

    path = save_credentials(api_url=api_url, api_token=api_token)
    print(f"Credentials saved to {path}")
    print(f"  API URL : {api_url}")
    print(f"  Token   : {api_token[:8]}{'*' * max(0, len(api_token) - 8)}")
    return 0


# ---------------------------------------------------------------------------
# hydrate / pull-blobs
# ---------------------------------------------------------------------------

def _cmd_hydrate(args: argparse.Namespace) -> int:
    from kerf_cli.hydrate import cmd_hydrate  # noqa: PLC0415
    return cmd_hydrate(args)


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

def _cmd_sync(args: argparse.Namespace) -> int:
    from kerf_cli.sync import cmd_sync  # noqa: PLC0415
    return cmd_sync(args)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def _cmd_export(args: argparse.Namespace) -> int:
    from kerf_cli.export import cmd_export  # noqa: PLC0415
    return cmd_export(args)


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

def _cmd_import(args: argparse.Namespace) -> int:
    from kerf_cli.import_ import cmd_import  # noqa: PLC0415
    return cmd_import(args)


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------

def _cmd_serve(args: argparse.Namespace) -> int:
    from kerf_cli.serve import run_serve  # noqa: PLC0415

    run_serve(
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        config=args.config or "",
        skip_migrate=args.skip_migrate,
    )
    return 0  # run_serve only returns when the server exits cleanly


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kerf",
        description=(
            "Kerf CLI — manage credentials and self-host a Kerf server.\n\n"
            "Cloud (default): set KERF_API_URL + KERF_API_TOKEN, or run "
            "`kerf login`.\n"
            "Self-host:       set DATABASE_URL, then run `kerf serve`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # ---- login ----
    login_p = sub.add_parser(
        "login",
        help="Store API token and server URL in ~/.config/kerf/credentials",
        description=(
            "Save credentials for the Kerf cloud (default) or a self-hosted "
            "instance.  Credentials are stored in ~/.config/kerf/credentials "
            "(mode 0600)."
        ),
    )
    login_p.add_argument(
        "--token",
        default="",
        metavar="TOKEN",
        help="API token (kerf_sk_…).  Prompted interactively if omitted.",
    )
    login_p.add_argument(
        "--api-url",
        default="",
        metavar="URL",
        help="Server URL (default: https://app.kerf.io).",
    )
    login_p.set_defaults(func=_cmd_login)

    # ---- serve ----
    serve_p = sub.add_parser(
        "serve",
        help="Start a self-hosted Kerf server (requires Postgres)",
        description=(
            "Start the Kerf backend.  DATABASE_URL must be set and reachable; "
            "if it is missing or the host is unreachable, the command prints "
            "a docker one-liner and exits with code 1."
        ),
    )
    serve_p.add_argument(
        "--host",
        default="0.0.0.0",
        metavar="HOST",
        help="Bind host (default: 0.0.0.0).",
    )
    serve_p.add_argument(
        "--port",
        type=int,
        default=8080,
        metavar="PORT",
        help="Bind port (default: 8080).",
    )
    serve_p.add_argument(
        "--reload",
        action="store_true",
        default=False,
        help="Enable auto-reload (development mode).",
    )
    serve_p.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="Number of worker processes (default: 1; ignored with --reload).",
    )
    serve_p.add_argument(
        "--config",
        default="",
        metavar="FILE",
        help="Path to kerf.toml config file.",
    )
    serve_p.add_argument(
        "--skip-migrate",
        action="store_true",
        default=False,
        help="Skip the migration step at startup.",
    )
    serve_p.set_defaults(func=_cmd_serve)

    # ---- hydrate (+ pull-blobs alias) ----
    _add_hydrate_parser(sub, "hydrate", alias=False)
    _add_hydrate_parser(sub, "pull-blobs", alias=True)

    # ---- sync ----
    _add_sync_parser(sub)

    # ---- export ----
    _add_export_parser(sub)

    # ---- import ----
    _add_import_parser(sub)

    # ---- admin ----
    from kerf_cli.admin import add_admin_parser  # noqa: PLC0415
    add_admin_parser(sub)

    return parser


def _add_hydrate_parser(
    sub: argparse._SubParsersAction,  # type: ignore[type-arg]
    name: str,
    *,
    alias: bool,
) -> None:
    """Register a hydrate (or pull-blobs alias) sub-parser onto *sub*."""
    desc_prefix = (
        "Resolve Git-LFS format pointer stubs to real bytes by fetching blobs\n"
        "from Kerf cloud storage.  Idempotent — already-hydrated files are skipped\n"
        "unless --force is given.\n\n"
    )
    if alias:
        desc_extra = (
            "This is an alias for `kerf hydrate`.  Use this spelling when the\n"
            "context is an explicit plain-git clone."
        )
    else:
        desc_extra = (
            "Run after a plain `git clone` to materialise all large files that\n"
            "were stored as LFS-format pointer stubs."
        )

    p = sub.add_parser(
        name,
        help=(
            "Fetch real bytes for LFS pointer stubs"
            if not alias
            else "Alias for `kerf hydrate`"
        ),
        description=desc_prefix + desc_extra,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "paths",
        nargs="*",
        metavar="path|glob",
        help=(
            "File paths or glob patterns to scan (default: entire working tree)."
        ),
    )
    p.add_argument(
        "--project",
        default="",
        metavar="ID",
        help=(
            "Kerf project UUID.  Inferred from .kerf/project or the git remote "
            "URL if omitted."
        ),
    )
    p.add_argument(
        "--url",
        default="",
        metavar="URL",
        help="Override the API endpoint (default: $KERF_API_URL or https://app.kerf.io).",
    )
    p.add_argument(
        "--token",
        default="",
        metavar="TOKEN",
        help="API token (kerf_sk_…).  $KERF_API_TOKEN is preferred.",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=4,
        metavar="N",
        help="Parallel blob fetches (default: 4).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List pointer stubs that would be fetched without writing any bytes.",
    )
    p.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Re-fetch and overwrite files that appear already hydrated.",
    )
    p.set_defaults(func=_cmd_hydrate)


# ---------------------------------------------------------------------------
# sync parser
# ---------------------------------------------------------------------------

def _add_sync_parser(
    sub: argparse._SubParsersAction,  # type: ignore[type-arg]
) -> None:
    """Register the `sync` sub-parser."""
    p = sub.add_parser(
        "sync",
        help="Two-way mirror between a local directory and a cloud project",
        description=(
            "Pull remote files to the local directory and push local changes\n"
            "back to the cloud project.  Change detection uses server-side\n"
            "updated_at vs local mtime (last-write-wins).  LFS pointer stubs\n"
            "are hydrated implicitly after pulling.\n\n"
            "A file deleted locally is NOT auto-deleted on the server — a\n"
            "warning is printed instead (safe default).\n\n"
            "KERF_API_URL / KERF_API_TOKEN or `kerf login` credentials are\n"
            "used for authentication."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "project_id",
        metavar="project-id",
        help="Kerf project UUID.",
    )
    p.add_argument(
        "local_dir",
        metavar="local-dir",
        help="Local directory to sync with the project.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="List the actions that would be taken without applying them.",
    )
    p.add_argument(
        "--url",
        default="",
        metavar="URL",
        help="Override the API endpoint (default: $KERF_API_URL or https://app.kerf.io).",
    )
    p.add_argument(
        "--token",
        default="",
        metavar="TOKEN",
        help="API token (kerf_sk_…).  $KERF_API_TOKEN is preferred.",
    )
    p.set_defaults(func=_cmd_sync)


# ---------------------------------------------------------------------------
# export parser
# ---------------------------------------------------------------------------

def _add_export_parser(
    sub: argparse._SubParsersAction,  # type: ignore[type-arg]
) -> None:
    """Register the `export` sub-parser."""
    p = sub.add_parser(
        "export",
        help="Materialise a project as a plain file tree on disk",
        description=(
            "Download a project from the Kerf server and write it as a\n"
            "plain directory tree.  The output directory contains all project\n"
            "files plus a .kerf/ sub-directory with:\n\n"
            "  .kerf/metadata.json  — project name, description, tags, IDs\n"
            "  .kerf/manifest.lock  — per-file SHA-256 OIDs + git/workspace info\n\n"
            "KERF_API_URL / KERF_API_TOKEN or `kerf login` credentials are\n"
            "used for authentication."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "project_id",
        metavar="project-id",
        help="Kerf project UUID.",
    )
    p.add_argument(
        "--out",
        default="",
        metavar="DIR",
        help=(
            "Output directory.  Defaults to kerf-export-<short-id> in the\n"
            "current working directory."
        ),
    )
    p.add_argument(
        "--url",
        default="",
        metavar="URL",
        help="Override the API endpoint (default: $KERF_API_URL or https://app.kerf.io).",
    )
    p.add_argument(
        "--token",
        default="",
        metavar="TOKEN",
        help="API token (kerf_sk_…).  $KERF_API_TOKEN is preferred.",
    )
    p.set_defaults(func=_cmd_export)


# ---------------------------------------------------------------------------
# import parser
# ---------------------------------------------------------------------------

def _add_import_parser(
    sub: argparse._SubParsersAction,  # type: ignore[type-arg]
) -> None:
    """Register the `import` sub-parser."""
    p = sub.add_parser(
        "import",
        help="Re-create a project from a materialised export directory",
        description=(
            "Read a directory produced by `kerf export`, create a new project\n"
            "via POST /api/projects, then upload each file.  The round-trip\n"
            "export → import produces a new project with identical file content.\n\n"
            "Project name comes from .kerf/metadata.json (--name overrides).\n"
            "Per-file SHA-256 OIDs in .kerf/manifest.lock are verified before\n"
            "upload so corrupted files are detected early.\n\n"
            "KERF_API_URL / KERF_API_TOKEN or `kerf login` credentials are\n"
            "used for authentication."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "import_dir",
        metavar="dir",
        help="Path to the export directory (produced by `kerf export`).",
    )
    p.add_argument(
        "--name",
        default="",
        metavar="NAME",
        help=(
            "Project name for the newly created project.  Defaults to the\n"
            "name stored in .kerf/metadata.json, or the directory name."
        ),
    )
    p.add_argument(
        "--url",
        default="",
        metavar="URL",
        help="Override the API endpoint (default: $KERF_API_URL or https://app.kerf.io).",
    )
    p.add_argument(
        "--token",
        default="",
        metavar="TOKEN",
        help="API token (kerf_sk_…).  $KERF_API_TOKEN is preferred.",
    )
    p.set_defaults(func=_cmd_import)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
