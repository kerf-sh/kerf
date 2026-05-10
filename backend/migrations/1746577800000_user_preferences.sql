-- Per-user UI preferences live in a single JSONB column on `users`.
--
-- The shape is small and all-optional; the backend validates the keys
-- against an allowlist (see handlers/me.go) and rejects unknown keys
-- with 400. We deliberately avoid a typed schema in the DB so that
-- adding a new pref doesn't require a migration — the allowlist is
-- the contract.
--
-- Today's keys (see CONTRACT.md / handlers.allowedPrefKeys):
--   default_model         string  e.g. "claude-opus-4-7"
--   units                 string  one of: "mm" | "cm" | "inches"
--   autosave_delay_ms     number  250..2000
--   eval_debounce_ms      number  100..1000
--   theme                 string  "system" | "dark"
--   reduce_motion         bool
--   compact_mode          bool

alter table users add column preferences jsonb not null default '{}'::jsonb;
