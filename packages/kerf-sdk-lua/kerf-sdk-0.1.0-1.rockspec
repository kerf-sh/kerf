package = "kerf-sdk"
version = "0.1.0-1"

source = {
  url = "git+https://github.com/kerf-sh/kerf-sdk-lua.git",
  tag = "sdk-lua-v0.1.0",
}

description = {
  summary  = "Lua SDK for Kerf — the parametric CAD platform.",
  detailed = [[
    JSON-RPC 2.0 client for the Kerf /v1/rpc endpoint.
    Provides namespaced wrappers for files, equations, configurations,
    revisions, and docs.  Auth via KERF_API_TOKEN environment variable
    or explicit token.  Returns (result, err) pairs using standard Lua
    idiom — no exceptions.
  ]],
  homepage = "https://kerf.app",
  license  = "MIT",
}

dependencies = {
  "lua >= 5.1",
  "luasocket",
  "luasec",
  "lua-cjson",
}

build = {
  type    = "builtin",
  modules = {
    ["kerf"]               = "kerf/init.lua",
    ["kerf.client"]        = "kerf/client.lua",
    ["kerf.error"]         = "kerf/error.lua",
    ["kerf.files"]         = "kerf/files.lua",
    ["kerf.equations"]     = "kerf/equations.lua",
    ["kerf.configurations"] = "kerf/configurations.lua",
    ["kerf.revisions"]     = "kerf/revisions.lua",
    ["kerf.docs"]          = "kerf/docs.lua",
  },
}
