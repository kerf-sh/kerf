from dataclasses import dataclass


@dataclass
class Money:
    amount: float
    currency: str


RATES = {
    "claude-opus-4-7": {"input_usd_per_mtok": 15.0, "output_usd_per_mtok": 75.0},
    "claude-sonnet-4-6": {"input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0},
    "claude-haiku-4-5": {"input_usd_per_mtok": 1.0, "output_usd_per_mtok": 5.0},
    "gpt-4o": {"input_usd_per_mtok": 2.50, "output_usd_per_mtok": 10.0},
    "gpt-4o-mini": {"input_usd_per_mtok": 0.15, "output_usd_per_mtok": 0.60},
    "o3-mini": {"input_usd_per_mtok": 1.10, "output_usd_per_mtok": 4.40},
    "gemini-2.5-pro": {"input_usd_per_mtok": 1.25, "output_usd_per_mtok": 5.0},
    "gemini-2.5-flash": {"input_usd_per_mtok": 0.075, "output_usd_per_mtok": 0.30},
    "kimi-k2-0905-preview": {"input_usd_per_mtok": 0.60, "output_usd_per_mtok": 2.50},
    "moonshot-v1-128k": {"input_usd_per_mtok": 0.60, "output_usd_per_mtok": 2.50},
    "moonshot-v1-32k": {"input_usd_per_mtok": 0.30, "output_usd_per_mtok": 1.20},
}

MEDIAN_RATE = {"input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0}

TIER_LIMITS = {
    "free": {
        "max_projects": 3,
        "storage_bytes": 50 * 1024 * 1024,
        "api_calls_per_month": 1000,
    },
    "starter": {
        "max_projects": 10,
        "storage_bytes": 1024 * 1024 * 1024,
        "api_calls_per_month": 10000,
    },
    "pro": {
        "max_projects": 50,
        "storage_bytes": 10 * 1024 * 1024 * 1024,
        "api_calls_per_month": 100000,
    },
    "enterprise": {
        "max_projects": -1,
        "storage_bytes": -1,
        "api_calls_per_month": -1,
    },
}


def lookup_rate(model: str) -> dict:
    if not model:
        return MEDIAN_RATE
    m = model.lower()
    if m in RATES:
        return RATES[m]
    best = ""
    for k in RATES:
        if m.startswith(k) and len(k) > len(best):
            best = k
    if best:
        return RATES[best]
    return MEDIAN_RATE


def token_cost(model: str, input_tokens: int, output_tokens: int, markup_pct: float) -> float:
    r = lookup_rate(model)
    raw = (input_tokens / 1_000_000.0) * r["input_usd_per_mtok"] + \
          (output_tokens / 1_000_000.0) * r["output_usd_per_mtok"]
    return raw * (1.0 + markup_pct / 100.0)


def storage_cost_per_gb_month(usd_per_gb_month: float) -> float:
    return usd_per_gb_month


def storage_daily_cost(bytes_count: int, usd_per_gb_month: float) -> float:
    gb = bytes_count / (1024.0 * 1024.0 * 1024.0)
    return gb * (usd_per_gb_month / 30.0)


def compute_price(workspace_tier: str, usage: dict) -> Money:
    markup_pct = 20.0
    storage_rate = 0.20

    total = 0.0

    if "input_tokens" in usage or "output_tokens" in usage:
        model = usage.get("model", "")
        input_tok = usage.get("input_tokens", 0)
        output_tok = usage.get("output_tokens", 0)
        total += token_cost(model, input_tok, output_tok, markup_pct)

    if "storage_bytes" in usage:
        total += storage_daily_cost(usage["storage_bytes"], storage_rate)

    if "api_calls" in usage:
        total += usage["api_calls"] * 0.001

    return Money(amount=total, currency="USD")


def get_tier_limits(tier: str) -> dict:
    return TIER_LIMITS.get(tier, TIER_LIMITS["free"])
