# kerf-sdk-go

Go SDK for [Kerf](https://kerf.app) — the parametric CAD platform.

## Install

```bash
go get github.com/kerf-sh/kerf-sdk-go
```

Requires Go 1.22+. Zero third-party dependencies — standard library only.

## Quickstart

```go
import (
    "context"
    kerf "github.com/kerf-sh/kerf-sdk-go"
)

k, err := kerf.FromEnv()   // reads KERF_API_TOKEN + KERF_API_URL
if err != nil {
    log.Fatal(err)
}

ctx := context.Background()
files, err := k.Files.List(ctx, "proj_123")
```

## Examples

**Read a file**

```go
content, err := k.Files.Read(ctx, "proj_123", "file_abc")
fmt.Println(content.Content)
```

**Set an equation variable**

```go
err := k.Equations.Set(ctx, "proj_123", "file_abc", "width", "75")
```

**Search the Kerf docs**

```go
hits, err := k.Docs.Search(ctx, "configurations", nil)
for _, h := range hits {
    fmt.Printf("[%.2f] %s\n", h.Score, h.Title)
}
```

## Auth

Set environment variables before running:

```bash
export KERF_API_TOKEN=kerf_sk_...
export KERF_API_URL=https://kerf.app   # optional, this is the default
```

Or construct with explicit values:

```go
k := kerf.New("https://kerf.app", "kerf_sk_...")
```

## Namespaces

| Namespace         | Methods                                               |
|-------------------|-------------------------------------------------------|
| `k.Files`         | `List`, `Read`, `Write`, `Edit`, `Create`, `Delete`, `Search` |
| `k.Equations`     | `Read`, `Set`                                         |
| `k.Configurations`| `List`, `Add`, `Activate`                             |
| `k.Revisions`     | `List`, `Read`, `Restore`                             |
| `k.Docs`          | `Search`                                              |

All methods accept `context.Context` as the first argument.

## Error handling

```go
_, err := k.Files.Read(ctx, "proj_123", "missing")
if errors.Is(err, kerf.ErrNotFound) {
    // handle 404
}
```

Sentinel errors: `kerf.ErrUnauthorized`, `kerf.ErrNotFound`, `kerf.ErrRateLimited`, `kerf.ErrMissingEnv`.

## Godoc

[pkg.go.dev/github.com/kerf-sh/kerf-sdk-go](https://pkg.go.dev/github.com/kerf-sh/kerf-sdk-go)

## License

MIT
