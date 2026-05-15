--- examples/quickstart.lua
--
-- Demonstrates the most common Kerf SDK operations.
--
-- Prerequisites:
--   luarocks install kerf-sdk
--
-- Auth: export KERF_API_TOKEN=kerf_sk_...
--       export KERF_API_URL=https://kerf.app   # optional default

local kerf = require "kerf"

-- Build a client from environment variables.
local k, err = kerf.from_env()
if err then
  io.stderr:write("kerf: " .. err.message .. "\n")
  os.exit(1)
end

local PROJECT = "proj_123"

-- List all files in a project.
local files, e = k.files:list(PROJECT)
if e then error(e.message) end

print(string.format("Files (%d):", #files))
for _, f in ipairs(files) do
  print(string.format("  %s  %s  [%s]", f.id, f.name, f.kind))
end

-- Read a specific file's content.
local file, e2 = k.files:read(PROJECT, "file_abc")
if e2 then error(e2.message) end
print("\nContent of " .. file.name .. ":\n" .. file.content)

-- Set an equation variable.
local _, e3 = k.equations:set(PROJECT, "file_abc", "width", "75")
if e3 then error(e3.message) end
print("\nEquation 'width' set to 75.")

-- Search the Kerf documentation.
local hits, e4 = k.docs:search("how to use configurations")
if e4 then error(e4.message) end
print(string.format("\nDoc results (%d):", #hits))
for _, h in ipairs(hits) do
  print(string.format("  [%.2f] %s", h.score, h.title))
end
