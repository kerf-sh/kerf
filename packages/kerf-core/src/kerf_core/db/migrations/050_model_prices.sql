-- model_prices: live per-(provider, model_id) chat-completion pricing.
--
-- Refreshed daily from LiteLLM's
-- model_prices_and_context_window.json by the kerf-pricing plugin.
-- Rates are stored per-Mtok (input/output/cache-read) so the table reads
-- naturally; the chat handler does (tokens / 1e6) * rate.
--
-- cheap_tier_eligible is NOT a copy of LiteLLM data — it's the Kerf product
-- decision about which models the free-tier monthly quota can be spent
-- against.  The refresh job sets it from a curated allow-list in
-- kerf_pricing/cheap_tier.py.
--
-- raw_json keeps the full upstream entry so we can re-derive any field we
-- didn't think to denormalise yet (cache-write rate, vision pricing, …).

create table if not exists model_prices (
    id                  uuid primary key default gen_random_uuid(),
    provider            text not null,
    model_id            text not null,
    input_per_mtok      numeric(10, 4) not null,
    output_per_mtok     numeric(10, 4) not null,
    cache_read_per_mtok numeric(10, 4),
    max_input_tokens    integer,
    cheap_tier_eligible boolean not null default false,
    raw_json            jsonb not null,
    fetched_at          timestamptz not null default now(),
    unique (provider, model_id)
);

create index if not exists model_prices_lookup on model_prices(provider, model_id);
create index if not exists model_prices_cheap_tier on model_prices(cheap_tier_eligible) where cheap_tier_eligible;
