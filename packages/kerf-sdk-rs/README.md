# kerf-sdk

Async Rust client for the [Kerf](https://kerf.sh) CAD platform JSON-RPC API.

```toml
[dependencies]
kerf-sdk = "0.1"
```

## Auth

```bash
export KERF_API_URL=https://kerf.sh
export KERF_API_TOKEN=ktok_...
```

## Usage

### Read a file

```rust
use kerf_sdk::Kerf;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let k = Kerf::from_env()?;
    let content = k.files.read("proj_123", "file_456").await?;
    println!("{}", content.content);
    Ok(())
}
```

### Set an equation

```rust
let k = Kerf::from_env()?;
k.equations.set("proj_123", "file_456", "width", "25 mm").await?;
```

### Search docs

```rust
let k = Kerf::from_env()?;
let hits = k.docs.search("assemblies", Some(5)).await?;
for hit in hits {
    println!("{}: {}", hit.title, hit.url);
}
```

## Namespaces

| Namespace | Methods |
|-----------|---------|
| `files` | `list`, `read`, `write`, `edit`, `create`, `delete`, `search` |
| `equations` | `read`, `set` |
| `configurations` | `list`, `add`, `activate` |
| `revisions` | `list`, `read`, `restore` |
| `docs` | `search` |

## Links

- [API docs on docs.rs](https://docs.rs/kerf-sdk)
- [Python SDK (kerf-sdk on PyPI)](https://pypi.org/project/kerf-sdk/)
- [Kerf documentation](https://kerf.sh/docs)
