--- kerf.client — JSON-RPC 2.0 transport over luasocket + luasec.
--
-- Wire format:
--   POST {api_url}/v1/rpc
--   Content-Type: application/json
--   Authorization: Bearer {api_token}
--   Body: {"jsonrpc":"2.0","method":"...","params":{...},"id":"<uuid>"}
--
-- Returns (result, err) on every call.  result is the decoded JSON value
-- from the "result" field.  On any error result == nil and err is a
-- KerfError table (see kerf.error).

local cjson  = require "cjson"
local http   = require "socket.http"
local https  = require "ssl.https"
local ltn12  = require "ltn12"
local kerr   = require "kerf.error"

local Client = {}
Client.__index = Client

--- _uuid4() -> string
-- Generates a random UUID v4 using math.random.
-- math.randomseed should have been called before the first call.
local function _uuid4()
  local t = {}
  for i = 1, 16 do t[i] = math.random(0, 255) end
  t[7] = (t[7] & 0x0f) | 0x40  -- version 4
  t[9] = (t[9] & 0x3f) | 0x80  -- variant 10xx
  return string.format(
    "%02x%02x%02x%02x-%02x%02x-%02x%02x-%02x%02x-%02x%02x%02x%02x%02x%02x",
    t[1],  t[2],  t[3],  t[4],
    t[5],  t[6],
    t[7],  t[8],
    t[9],  t[10],
    t[11], t[12], t[13], t[14], t[15], t[16]
  )
end

-- Seed once when the module loads so IDs are not trivially predictable.
math.randomseed(os.time())

--- new(api_url, api_token) -> Client
-- Constructs a raw JSON-RPC client.  Prefer kerf.connect() or kerf.from_env().
function Client.new(api_url, api_token)
  assert(api_url,   "kerf: api_url is required")
  assert(api_token, "kerf: api_token is required")
  return setmetatable({
    _api_url   = api_url:gsub("/+$", ""),
    _api_token = api_token,
  }, Client)
end

--- call(method, params) -> result, err
-- Sends a single JSON-RPC 2.0 request and returns the decoded result.
-- On any failure returns nil, KerfError.
function Client:call(method, params)
  local payload = cjson.encode({
    jsonrpc = "2.0",
    method  = method,
    params  = params or {},
    id      = _uuid4(),
  })

  local url        = self._api_url .. "/v1/rpc"
  local response   = {}
  local use_https  = url:sub(1, 5) == "https"
  local driver     = use_https and https or http

  local _, status, headers = driver.request({
    url     = url,
    method  = "POST",
    headers = {
      ["Content-Type"]   = "application/json",
      ["Content-Length"] = tostring(#payload),
      ["Authorization"]  = "Bearer " .. self._api_token,
    },
    source = ltn12.source.string(payload),
    sink   = ltn12.sink.table(response),
  })

  if type(status) ~= "number" then
    -- luasocket returns an error string instead of a status code on failure.
    return nil, kerr.new(kerr.RPC_ERROR, tostring(status))
  end

  if status < 200 or status >= 300 then
    return nil, kerr.new(kerr.RPC_ERROR, string.format("kerf: http %d", status))
  end

  local body = table.concat(response)
  local ok, decoded = pcall(cjson.decode, body)
  if not ok then
    return nil, kerr.new(kerr.RPC_ERROR, "kerf: invalid JSON response")
  end

  if decoded.error ~= nil and decoded.error ~= cjson.null then
    local e = decoded.error
    return nil, kerr.new(e.code or kerr.RPC_ERROR, e.message or "unknown error", e.data)
  end

  -- decoded.result may be cjson.null — caller can test result == cjson.null
  return decoded.result, nil
end

return Client
