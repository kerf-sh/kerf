--- kerf.error — KerfError table + well-known RPC error codes.
--
-- Every public API call returns (result, err).  On failure result == nil
-- and err is a KerfError table:  { code, message, data }.
--
-- Check by code:
--   local r, err = k.files:list("proj_123")
--   if err then
--     if err.code == kerf_error.UNAUTHORIZED then ... end
--   end

local M = {}

-- Well-known JSON-RPC error codes used by the Kerf backend.
M.MISSING_ENV   = -32000  -- required env var absent (client-side)
M.UNAUTHORIZED  = -32001  -- invalid or missing API token
M.NOT_FOUND     = -32004  -- resource does not exist
M.RPC_ERROR     = -32603  -- internal / transport error
M.RATE_LIMITED  = -32429  -- too many requests

--- new(code, message[, data]) -> KerfError table
-- Constructs a KerfError.  data is optional extra context from the server.
function M.new(code, message, data)
  return {
    code    = code,
    message = message,
    data    = data,
    -- Convenience: tostring(err) prints the same format as Go/Python SDKs.
    __tostring = function(self)
      return string.format("kerf: %d %s", self.code, self.message)
    end,
  }
end

return M
