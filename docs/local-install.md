# Local install

How to self-host Kerf on your own machine or a private server. Kerf is fully
open-source (MIT) for the core; no account or network access is required.

## Install paths

### Homebrew (coming soon)

```sh
brew install kerf-sh/tap/kerf
```

### One-shot installer

```sh
curl -fsSL https://kerf.sh/install.sh | sh
```

The script installs the `kerf` Python package and the `kerf-server` CLI.

### From PyPI (explicit persona)

```sh
pip install "kerf[mech]"          # mechanical CAD
pip install "kerf[electronics]"   # EDA / PCB
pip install "kerf[bim]"           # building information modelling
pip install "kerf[full]"          # everything
```

### From source

```sh
git clone https://github.com/kerf-sh/kerf
cd kerf
pip install -e .[mech]    # choose your persona
npm install
```

See [getting-started.md](./getting-started.md) for the full from-source walkthrough.

## Persona bundles

Pick the persona that covers your domain. Smaller personas install faster and
have lighter runtime footprints.

| Persona | Use when | Heavy deps added |
|---------|----------|-----------------|
| `api-only` | You need just the REST + RPC surface (e.g. a headless API pod) | none |
| `mech` | Mechanical CAD, FEM, CAM, topology optimisation | pythonOCC, FEniCSx, OpenCAMlib |
| `electronics` | PCB, schematics, SPICE, RF | ngspice, scikit-rf |
| `bim` | Building modelling, IFC export | IfcOpenShell |
| `full` | All of the above + cloud plugins | everything |
| `compute-only` | Heavy workers behind an internal load balancer; no auth or REST | all compute deps |

Full breakdown: [persona-bundles.md](./persona-bundles.md).

## Postgres setup

Kerf requires Postgres 14 or newer.

```sh
# macOS (Homebrew)
brew install postgresql@16
brew services start postgresql@16
createdb kerf

# Ubuntu / Debian
sudo apt install postgresql
sudo -u postgres createdb kerf
sudo -u postgres psql -c "CREATE USER myuser WITH PASSWORD 'mypass';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE kerf TO myuser;"
```

Set the database URL in `kerf.toml`:

```toml
[database]
url = "postgres://myuser:mypass@localhost:5432/kerf?sslmode=disable"
```

Or via environment variable:

```sh
export DATABASE_URL=postgres://myuser:mypass@localhost:5432/kerf?sslmode=disable
```

## First-run setup

```sh
# Create and initialise the database
createdb kerf
kerf-server --migrate   # runs all migrations; safe to re-run

# Start the server (serves on http://localhost:8080)
kerf-server
```

On first load with `local_mode = true` (the default), the server auto-creates
a system user and signs you in without a login screen.

## Single-user vs multi-user

| Setting | Behaviour |
|---------|-----------|
| `[server].local_mode = true` (default) | No login screen. A singleton user is bootstrapped automatically. Ideal for a personal workstation install. |
| `[server].local_mode = false` | Standard register/login flow. Use for shared servers with multiple accounts. |

The hosted cloud tier (`[cloud].enabled = true`) always forces multi-user mode
regardless of `local_mode`. This is a cloud-only feature — it is not available
in the OSS build unless the proprietary `kerf-billing` + `kerf-cloud` packages
are installed.

## Config layering

Kerf reads configuration from the first file found, in priority order:

1. `--config <path>` CLI flag
2. `KERF_CONFIG` environment variable
3. `./kerf.toml` (current working directory)
4. `~/.config/kerf/config.toml`
5. `/etc/kerf/config.toml`

The server emits a starter `kerf.toml` on `npm run init` (source installs) or
on `kerf-server --init`. Full schema: `kerf.example.toml` in the repo root, or
[configuration.md](./configuration.md).

## Environment variables

Any `kerf.toml` key can be overridden with an environment variable. The
mapping follows the TOML path with underscores and a `KERF_` prefix:

| Env var | Equivalent TOML key |
|---------|---------------------|
| `KERF_CONFIG` | path to config file (meta) |
| `KERF_HOST` | `[server].host` |
| `KERF_PORT` | `[server].port` |
| `DATABASE_URL` | `[database].url` |
| `KERF_LOCAL_MODE` | `[server].local_mode` |
| `CLOUD_ENABLED` | `[cloud].enabled` |
| `ANTHROPIC_API_KEY` | `[llm.anthropic].api_key` |
| `OPENAI_API_KEY` | `[llm.openai].api_key` |

## Storage backends

Three backends are available:

| Backend | Config key | Notes |
|---------|------------|-------|
| `local` | `[storage].backend = "local"` | Opaque blob store under `[storage].local_path`. Default for dev. |
| `s3` | `[storage].backend = "s3"` | AWS S3, Cloudflare R2, or MinIO. Configure `[storage.s3]`. |
| `filesystem` | `[storage].backend = "filesystem"` | Projects mirror to disk under `[storage].filesystem_root`. Each project is a real folder — edit files with your own tools. |

The `git` backend (cloud-only) sits above S3 and adds a per-project bare repo.
Not available in the OSS install.

## Upgrading

Migrations are safe to re-run. Always run `--migrate` after pulling a new
version:

```sh
git pull
pip install -e .[mech]    # pick up any new deps
kerf-server --migrate
kerf-server
```

## Uninstall

```sh
pip uninstall kerf kerf-core kerf-api kerf-chat  # etc.
dropdb kerf                                       # drops the database
rm -rf ~/.config/kerf                             # config + auth state
rm -rf ./.kerf-storage                            # local blob store (if used)
```

## See also

- [getting-started.md](./getting-started.md) — step-by-step first run
- [configuration.md](./configuration.md) — full config schema
- [persona-bundles.md](./persona-bundles.md) — which plugins each persona includes
- [deployment.md](./deployment.md) — Docker + production deploy
