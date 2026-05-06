-- Kerf seed. Idempotent. Substituted by cmd/migrate via text/template.
-- Template variables (substituted in Go): .SystemEmail .SystemName
-- SQL parameters (passed via tx.Exec): $1 = bcrypt(systemPassword + pepper)
--
-- Re-running this seed should be safe: the system user is upserted by email,
-- and any other rows here MUST also be guarded with `on conflict ... do ...`.

insert into users (id, email, name, password_hash, account_role, is_system)
values (gen_random_uuid(), '{{.SystemEmail}}', '{{.SystemName}}', $1, 'system', true)
on conflict (email) do update set
  account_role  = 'system',
  is_system     = true,
  password_hash = excluded.password_hash,
  name          = excluded.name;
