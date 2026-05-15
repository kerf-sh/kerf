# kerf-sdk-lua

Lua SDK for [Kerf](https://kerf.app) — the parametric CAD platform.

## Install

```bash
luarocks install kerf-sdk
```

Requires Lua 5.1+ (LuaJIT compatible). Dependencies: `luasocket`, `luasec`, `lua-cjson`.

## Quickstart

```lua
local kerf = require "kerf"

local k, err = kerf.from_env()   -- reads KERF_API_TOKEN + KERF_API_URL
if err then error(err.message) end

local files, e = k.files:list("proj_123")
if e then error(e.message) end

for _, f in ipairs(files) do
  print(f.id, f.name, f.kind)
end
```

## Auth

```bash
export KERF_API_TOKEN=kerf_sk_...
export KERF_API_URL=https://kerf.app   # optional, this is the default
```

Or construct explicitly:

```lua
local k = kerf.connect({ api_url = "https://kerf.app", api_token = "kerf_sk_..." })
```

## Namespaces

| Namespace              | Methods                                                      |
|------------------------|--------------------------------------------------------------|
| `k.files`              | `list`, `read`, `write`, `create`, `delete`                  |
| `k.equations`          | `read`, `set`                                                |
| `k.configurations`     | `list`, `activate`                                           |
| `k.revisions`          | `list`, `read`, `restore`                                    |
| `k.docs`               | `search`                                                     |

All methods use colon syntax and return `(result, err)`.

## Error handling

```lua
local result, err = k.files:read("proj_123", "missing")
if err then
  if err.code == kerf.error.NOT_FOUND then
    print("file not found")
  else
    error(err.message)
  end
end
```

Error codes: `kerf.error.UNAUTHORIZED` (`-32001`), `kerf.error.NOT_FOUND` (`-32004`),
`kerf.error.RATE_LIMITED` (`-32429`), `kerf.error.RPC_ERROR` (`-32603`),
`kerf.error.MISSING_ENV` (`-32000`).

## Running the tests

```bash
lua spec/client_spec.lua
```

No external test framework required. The suite also works with `busted` if it is installed.

## License

MIT
