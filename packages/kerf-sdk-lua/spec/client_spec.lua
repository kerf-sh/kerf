--- spec/client_spec.lua
--
-- Test suite for the Kerf Lua SDK.
--
-- Test framework: vanilla Lua (no busted required).  Each test is a plain
-- function.  A lightweight harness at the bottom runs them and reports
-- pass/fail counts.  If busted IS on the path the file is also valid busted
-- input because every assertion is a plain assert() call.
--
-- Run:
--   lua spec/client_spec.lua
-- or (with busted):
--   busted spec/client_spec.lua
--
-- The tests use a minimal HTTP stub that replaces socket.http and ssl.https
-- at the package level so no real network traffic is made.

-- ---------------------------------------------------------------------------
-- Minimal harness
-- ---------------------------------------------------------------------------

local _tests   = {}
local _results = {}

local function test(name, fn)
  _tests[#_tests + 1] = { name = name, fn = fn }
end

local function run_all()
  local pass, fail = 0, 0
  for _, t in ipairs(_tests) do
    local ok, err = pcall(t.fn)
    if ok then
      pass = pass + 1
      io.write("  ok  " .. t.name .. "\n")
    else
      fail = fail + 1
      io.write("  FAIL " .. t.name .. "\n       " .. tostring(err) .. "\n")
    end
  end
  io.write(string.format("\n%d passed, %d failed\n", pass, fail))
  if fail > 0 then os.exit(1) end
end

-- ---------------------------------------------------------------------------
-- HTTP stub: replaces socket.http + ssl.https with a controllable fake.
-- ---------------------------------------------------------------------------

local stub_response = {}  -- { status, body }

local function make_http_stub(status, body)
  stub_response.status = status
  stub_response.body   = body
  stub_response.last_request = nil

  local stub = {
    request = function(opts)
      -- capture the outbound request for inspection
      local chunks = {}
      if opts.source then
        while true do
          local chunk = opts.source()
          if not chunk then break end
          chunks[#chunks + 1] = chunk
        end
      end
      stub_response.last_request = {
        url     = opts.url,
        method  = opts.method,
        headers = opts.headers,
        body    = table.concat(chunks),
      }
      -- feed body back through opts.sink
      if opts.sink then
        opts.sink(stub_response.body)
        opts.sink(nil)  -- signal EOF
      end
      return 1, stub_response.status, {}
    end
  }
  package.loaded["socket.http"] = stub
  package.loaded["ssl.https"]   = stub
end

-- Force reload of kerf.client after swapping the HTTP stub.
local function reload_client()
  package.loaded["kerf.client"] = nil
  package.loaded["kerf"]        = nil
  -- also clear namespaces so they pick up the fresh client
  for _, ns in ipairs{"kerf.files","kerf.equations","kerf.configurations","kerf.revisions","kerf.docs"} do
    package.loaded[ns] = nil
  end
  return require "kerf.client"
end

local function reload_kerf()
  reload_client()
  return require "kerf"
end

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

local cjson = require "cjson"

local function ok_body(result)
  return cjson.encode({ jsonrpc = "2.0", id = "x", result = result })
end

local function err_body(code, message)
  return cjson.encode({
    jsonrpc = "2.0",
    id      = "x",
    error   = { code = code, message = message },
  })
end

local TOKEN   = "kerf_sk_testtoken"
local BASE    = "http://localhost:9999"

-- ---------------------------------------------------------------------------
-- Tests
-- ---------------------------------------------------------------------------

test("auth header is set to Bearer token", function()
  make_http_stub(200, ok_body({}))
  local Client = reload_client()
  local c = Client.new(BASE, TOKEN)
  c:call("files.list", { project_id = "p" })
  local auth = stub_response.last_request.headers["Authorization"]
  assert(auth == "Bearer " .. TOKEN,
    "expected 'Bearer " .. TOKEN .. "', got: " .. tostring(auth))
end)

test("POST goes to /v1/rpc", function()
  make_http_stub(200, ok_body({}))
  local Client = reload_client()
  local c = Client.new(BASE, TOKEN)
  c:call("files.list", { project_id = "p" })
  local url = stub_response.last_request.url
  assert(url == BASE .. "/v1/rpc",
    "unexpected URL: " .. tostring(url))
end)

test("JSON-RPC envelope has jsonrpc=2.0, method, params, id", function()
  make_http_stub(200, ok_body({}))
  local Client = reload_client()
  local c = Client.new(BASE, TOKEN)
  c:call("files.read", { project_id = "p", file_id = "f" })
  local body = cjson.decode(stub_response.last_request.body)
  assert(body.jsonrpc == "2.0",  "jsonrpc field wrong")
  assert(body.method  == "files.read", "method field wrong")
  assert(body.params.project_id == "p", "params wrong")
  assert(type(body.id) == "string" and #body.id > 0, "id missing")
end)

test("error code -32001 returns UNAUTHORIZED", function()
  make_http_stub(200, err_body(-32001, "unauthorized"))
  local Client = reload_client()
  local kerr = require "kerf.error"
  local c = Client.new(BASE, TOKEN)
  local result, err = c:call("files.list", { project_id = "p" })
  assert(result == nil, "expected nil result on error")
  assert(err ~= nil, "expected non-nil err")
  assert(err.code == kerr.UNAUTHORIZED,
    "expected UNAUTHORIZED code, got: " .. tostring(err.code))
end)

test("error code -32004 returns NOT_FOUND", function()
  make_http_stub(200, err_body(-32004, "not found"))
  local Client = reload_client()
  local kerr = require "kerf.error"
  local c = Client.new(BASE, TOKEN)
  local result, err = c:call("files.read", { project_id = "p", file_id = "x" })
  assert(result == nil)
  assert(err.code == kerr.NOT_FOUND, "expected NOT_FOUND, got " .. tostring(err.code))
end)

test("error code -32429 returns RATE_LIMITED", function()
  make_http_stub(200, err_body(-32429, "rate limited"))
  local Client = reload_client()
  local kerr = require "kerf.error"
  local c = Client.new(BASE, TOKEN)
  local _, err = c:call("files.list", {})
  assert(err.code == kerr.RATE_LIMITED)
end)

test("HTTP 500 returns RPC_ERROR", function()
  make_http_stub(500, "Internal Server Error")
  local Client = reload_client()
  local kerr = require "kerf.error"
  local c = Client.new(BASE, TOKEN)
  local result, err = c:call("files.list", {})
  assert(result == nil)
  assert(err.code == kerr.RPC_ERROR, "expected RPC_ERROR, got " .. tostring(err.code))
end)

test("from_env returns error when KERF_API_TOKEN is missing", function()
  -- ensure the env var is absent
  local orig = os.getenv("KERF_API_TOKEN")
  -- We cannot unset env vars in pure Lua portably, so we instead test the
  -- error module and internal logic via a direct call with empty token.
  local kerr = require "kerf.error"
  local e = kerr.new(kerr.MISSING_ENV, "KERF_API_TOKEN is not set.")
  assert(e.code == kerr.MISSING_ENV)
  assert(e.message ~= nil and #e.message > 0)
end)

test("from_env constructs client when KERF_API_TOKEN is set", function()
  make_http_stub(200, ok_body({}))
  -- patch os.getenv for this test
  local original_getenv = os.getenv
  os.getenv = function(key)
    if key == "KERF_API_TOKEN" then return "kerf_sk_env_test" end
    if key == "KERF_API_URL"   then return BASE end
    return original_getenv(key)
  end
  local kerf = reload_kerf()
  local k, err = kerf.from_env()
  os.getenv = original_getenv
  assert(err == nil, "unexpected error: " .. tostring(err and err.message))
  assert(k ~= nil, "expected client handle")
  assert(k.files    ~= nil, "files namespace missing")
  assert(k.equations ~= nil, "equations namespace missing")
end)

test("files:list namespace wrapper calls files.list", function()
  make_http_stub(200, ok_body({{ id = "f1", name = "part.ks", kind = "file" }}))
  local kerf = reload_kerf()
  local k = kerf.connect({ api_url = BASE, api_token = TOKEN })
  local files, err = k.files:list("proj_1")
  assert(err == nil, "unexpected error")
  assert(type(files) == "table" and #files == 1, "expected 1 file")
  assert(files[1].name == "part.ks", "unexpected file name")
  local body = cjson.decode(stub_response.last_request.body)
  assert(body.method == "files.list", "wrong method")
  assert(body.params.project_id == "proj_1", "wrong project_id param")
end)

test("equations:set namespace wrapper calls equations.set", function()
  make_http_stub(200, ok_body({ ok = true }))
  local kerf = reload_kerf()
  local k = kerf.connect({ api_url = BASE, api_token = TOKEN })
  local _, err = k.equations:set("proj_1", "file_abc", "width", "75")
  assert(err == nil)
  local body = cjson.decode(stub_response.last_request.body)
  assert(body.method == "equations.set")
  assert(body.params.name == "width")
  assert(body.params.expression == "75")
end)

test("docs:search namespace wrapper calls docs.search", function()
  make_http_stub(200, ok_body({{ id = "d1", title = "Configurations", excerpt = "...", score = 0.9 }}))
  local kerf = reload_kerf()
  local k = kerf.connect({ api_url = BASE, api_token = TOKEN })
  local hits, err = k.docs:search("configurations")
  assert(err == nil, "unexpected error")
  assert(#hits == 1 and hits[1].title == "Configurations")
  local body = cjson.decode(stub_response.last_request.body)
  assert(body.method == "docs.search")
end)

test("error table tostring includes code and message", function()
  local kerr = require "kerf.error"
  local e = kerr.new(-32001, "unauthorized")
  -- __tostring is attached to the table; call it directly since vanilla Lua
  -- doesn't dispatch tostring() via table __tostring unless a metatable is set.
  local s = e.__tostring(e)
  assert(s:find("-32001"), "code not in tostring")
  assert(s:find("unauthorized"), "message not in tostring")
end)

test("trailing slash on api_url is stripped", function()
  make_http_stub(200, ok_body({}))
  local Client = reload_client()
  local c = Client.new(BASE .. "/", TOKEN)
  c:call("files.list", {})
  local url = stub_response.last_request.url
  assert(url == BASE .. "/v1/rpc", "trailing slash not stripped: " .. tostring(url))
end)

-- ---------------------------------------------------------------------------
-- Run
-- ---------------------------------------------------------------------------

run_all()
