"""T-56  Distributors integration — hermetic pytest suite.

Covers:
  - 25 part lookups across mocked DigiKey / Mouser / LCSC providers
  - FX conversion (CNY→USD via mocked fx helper)
  - Cache TTL behaviour (sync.is_stale + fx.Fetcher in-memory cache)
  - Error paths: auth failures, empty results, rate-limit, malformed responses
  - Registry.has / Registry.acquire / refresh_part happy + sad paths

No DB, no network.  All HTTP is intercepted via unittest.mock.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kerf_cloud.distributors.service import (
    PROVIDER_DIGIKEY,
    PROVIDER_LCSC,
    PROVIDER_MOUSER,
    Credentials,
    DistributorAuthError,
    DistributorNotFound,
    DistributorPart,
)
from kerf_cloud.distributors.sync import STALE_PART_AGE, is_stale, refresh_part

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UTC = timezone.utc


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _old_iso(hours: int = 30) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def _part_doc(providers: list[str], fetched_at: str | None = None) -> str:
    dists = []
    for p in providers:
        entry: dict = {"name": p, "sku": f"SKU-{p.upper()}-001"}
        if fetched_at is not None:
            entry["fetched_at"] = fetched_at
        dists.append(entry)
    return json.dumps({"name": "test-part", "mpn": "MPNXYZ", "distributors": dists})


# ---------------------------------------------------------------------------
# Async FX mock helper
# ---------------------------------------------------------------------------


def _mock_fx(rate: float = 0.14, ok: bool = True):
    """Return an async-compatible FX helper stub that reports CNY→USD rate."""
    fx = AsyncMock()
    fx.rate = AsyncMock(return_value=(rate, datetime.now(UTC), ok))
    return fx


# ---------------------------------------------------------------------------
# 1–5  DigiKey mocked lookups
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_digikey_search_returns_parts():
    """T-56-1  DigiKey search: single result parsed correctly."""
    from kerf_cloud.distributors.digikey import DigiKeyService

    svc = DigiKeyService(Credentials(client_id="id", client_secret="sec"))

    token_resp = MagicMock()
    token_resp.status = 200
    token_resp.text = AsyncMock(
        return_value=json.dumps({"access_token": "tok", "expires_in": 3600})
    )
    token_resp.__aenter__ = AsyncMock(return_value=token_resp)
    token_resp.__aexit__ = AsyncMock(return_value=False)

    product = {"DigiKeyPartNumber": "DK-RES-001", "ProductUrl": "https://digikey.com/p/1", "UnitPrice": 0.05, "QuantityAvailable": 5000}
    search_resp = MagicMock()
    search_resp.status = 200
    search_resp.text = AsyncMock(return_value=json.dumps({"Products": [product]}))
    search_resp.__aenter__ = AsyncMock(return_value=search_resp)
    search_resp.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(side_effect=[token_resp, search_resp])
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=session):
        results = await svc.search(None, "100R resistor", 5)

    assert len(results) == 1
    assert results[0].sku == "DK-RES-001"
    assert results[0].price_usd == pytest.approx(0.05)
    assert results[0].stock == 5000


@pytest.mark.asyncio
async def test_digikey_lookup_delegates_to_search():
    """T-56-2  DigiKey lookup() calls search() and returns first result."""
    from kerf_cloud.distributors.digikey import DigiKeyService

    svc = DigiKeyService(Credentials(client_id="id", client_secret="sec"))

    fake_result = DistributorPart(name=PROVIDER_DIGIKEY, sku="DK-CAP-022", price_usd=0.12, stock=1000)
    svc.search = AsyncMock(return_value=[fake_result])

    part = await svc.lookup(None, "DK-CAP-022")
    assert part.sku == "DK-CAP-022"
    svc.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_digikey_lookup_empty_sku_raises():
    """T-56-3  DigiKey lookup() with empty SKU raises DistributorNotFound."""
    from kerf_cloud.distributors.digikey import DigiKeyService

    svc = DigiKeyService(Credentials(client_id="id", client_secret="sec"))
    with pytest.raises(DistributorNotFound):
        await svc.lookup(None, "")


@pytest.mark.asyncio
async def test_digikey_lookup_no_results_raises():
    """T-56-4  DigiKey lookup() with no search results raises DistributorNotFound."""
    from kerf_cloud.distributors.digikey import DigiKeyService

    svc = DigiKeyService(Credentials(client_id="id", client_secret="sec"))
    svc.search = AsyncMock(return_value=[])

    with pytest.raises(DistributorNotFound):
        await svc.lookup(None, "UNKNOWN-SKU")


@pytest.mark.asyncio
async def test_digikey_auth_error_propagates():
    """T-56-5  DigiKey raises DistributorAuthError on 401 token response."""
    from kerf_cloud.distributors.digikey import DigiKeyService

    svc = DigiKeyService(Credentials(client_id="id", client_secret="bad"))

    token_resp = MagicMock()
    token_resp.status = 401
    token_resp.text = AsyncMock(return_value="Unauthorized")
    token_resp.__aenter__ = AsyncMock(return_value=token_resp)
    token_resp.__aexit__ = AsyncMock(return_value=False)

    session = MagicMock()
    session.post = MagicMock(return_value=token_resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=session):
        with pytest.raises(DistributorAuthError):
            await svc.search(None, "resistor", 3)


# ---------------------------------------------------------------------------
# 6–10  Mouser mocked lookups
# ---------------------------------------------------------------------------


def _mouser_svc() -> object:
    from kerf_cloud.distributors.mouser import MouserService
    return MouserService(Credentials(api_key="mouser-key-abc"))


def _mouser_resp(parts: list[dict]) -> MagicMock:
    resp = MagicMock()
    resp.status = 200
    resp.text = AsyncMock(
        return_value=json.dumps(
            {"Errors": [], "SearchResults": {"Parts": parts}}
        )
    )
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_mouser_search_single_part():
    """T-56-6  Mouser search: single part with price break parsed."""
    svc = _mouser_svc()
    part = {"MouserPartNumber": "MO-CAP-001", "ProductDetailUrl": "https://mouser.com/c/1", "PriceBreaks": [{"Price": "$0.10"}], "Availability": "3000"}
    session = _mouser_resp([part])
    with patch("aiohttp.ClientSession", return_value=session):
        results = await svc.search(None, "100nF cap", 5)
    assert len(results) == 1
    assert results[0].sku == "MO-CAP-001"
    assert results[0].price_usd == pytest.approx(0.10)
    assert results[0].stock == 3000


@pytest.mark.asyncio
async def test_mouser_search_multiple_parts():
    """T-56-7  Mouser search: multiple parts returned up to limit."""
    svc = _mouser_svc()
    parts = [
        {"MouserPartNumber": f"MO-R-{i:03d}", "PriceBreaks": [{"Price": f"${i * 0.01:.2f}"}], "Availability": str(i * 100)}
        for i in range(1, 6)
    ]
    session = _mouser_resp(parts)
    with patch("aiohttp.ClientSession", return_value=session):
        results = await svc.search(None, "resistor", 5)
    assert len(results) == 5
    assert results[2].sku == "MO-R-003"


@pytest.mark.asyncio
async def test_mouser_empty_search_returns_empty():
    """T-56-8  Mouser search with empty query returns empty list (no HTTP call)."""
    svc = _mouser_svc()
    results = await svc.search(None, "", 10)
    assert results == []


@pytest.mark.asyncio
async def test_mouser_lookup_not_found():
    """T-56-9  Mouser lookup raises DistributorNotFound when search empty."""
    svc = _mouser_svc()
    svc.search = AsyncMock(return_value=[])
    with pytest.raises(DistributorNotFound):
        await svc.lookup(None, "GHOST-SKU")


@pytest.mark.asyncio
async def test_mouser_price_parse_no_dollar():
    """T-56-10  Mouser price parser handles prices without $ prefix."""
    from kerf_cloud.distributors.mouser import MouserService
    svc = MouserService(Credentials(api_key="k"))
    # "0.25 USD" style
    assert svc._parse_price([{"Price": "0.25 USD"}]) == pytest.approx(0.25)
    assert svc._parse_price([{"Price": "$1,234.56"}]) == pytest.approx(1234.56)
    assert svc._parse_price([]) == 0.0


# ---------------------------------------------------------------------------
# 11–17  LCSC mocked lookups + FX conversion
# ---------------------------------------------------------------------------


def _lcsc_svc(fx=None):
    from kerf_cloud.distributors.lcsc import LCSCService
    return LCSCService(Credentials(api_key="lcsc-k"), fx=fx)


def _lcsc_session(products: list[dict], status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=json.dumps({"result": {"productList": products}}))
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


@pytest.mark.asyncio
async def test_lcsc_search_no_fx():
    """T-56-11  LCSC search without FX: price_usd is None."""
    svc = _lcsc_svc(fx=None)
    products = [{"productCode": "C001", "productUrl": "https://lcsc.com/c001", "productPriceList": [{"ladderLevel": 1, "productPrice": 0.80}], "stockNumber": 10000}]
    with patch("aiohttp.ClientSession", return_value=_lcsc_session(products)):
        results = await svc.search(None, "C001", 5)
    assert len(results) == 1
    assert results[0].sku == "C001"
    assert results[0].price_usd is None
    assert results[0].raw["price_cny"] == pytest.approx(0.80)


@pytest.mark.asyncio
async def test_lcsc_search_with_fx_converts_price():
    """T-56-12  LCSC search with FX: CNY price converted to USD."""
    fx = _mock_fx(rate=0.14)
    svc = _lcsc_svc(fx=fx)
    products = [{"productCode": "C002", "productUrl": "", "productPriceList": [{"ladderLevel": 1, "productPrice": 1.0}], "stockNumber": 500}]
    with patch("aiohttp.ClientSession", return_value=_lcsc_session(products)):
        results = await svc.search(None, "C002", 5)
    assert len(results) == 1
    assert results[0].price_usd == pytest.approx(0.14)  # 1.0 CNY * 0.14


@pytest.mark.asyncio
async def test_lcsc_search_fx_unavailable_no_price():
    """T-56-13  LCSC search: FX rate unavailable (ok=False) → price_usd is None."""
    fx = _mock_fx(rate=0.0, ok=False)
    svc = _lcsc_svc(fx=fx)
    products = [{"productCode": "C003", "productPriceList": [{"ladderLevel": 1, "productPrice": 2.5}], "stockNumber": 200}]
    with patch("aiohttp.ClientSession", return_value=_lcsc_session(products)):
        results = await svc.search(None, "C003", 5)
    assert results[0].price_usd is None


@pytest.mark.asyncio
async def test_lcsc_search_fallback_to_first_price():
    """T-56-14  LCSC uses first price break when ladderLevel==1 not present."""
    fx = _mock_fx(rate=0.14)
    svc = _lcsc_svc(fx=fx)
    products = [{"productCode": "C004", "productPriceList": [{"ladderLevel": 5, "productPrice": 3.0}], "stockNumber": 0}]
    with patch("aiohttp.ClientSession", return_value=_lcsc_session(products)):
        results = await svc.search(None, "C004", 1)
    assert results[0].price_usd == pytest.approx(3.0 * 0.14)


@pytest.mark.asyncio
async def test_lcsc_empty_query_returns_empty():
    """T-56-15  LCSC search with empty query skips HTTP."""
    svc = _lcsc_svc()
    results = await svc.search(None, "", 5)
    assert results == []


@pytest.mark.asyncio
async def test_lcsc_lookup_not_found():
    """T-56-16  LCSC lookup raises DistributorNotFound when no results."""
    svc = _lcsc_svc()
    svc.search = AsyncMock(return_value=[])
    with pytest.raises(DistributorNotFound):
        await svc.lookup(None, "UNKNOWN")


@pytest.mark.asyncio
async def test_lcsc_search_zero_stock():
    """T-56-17  LCSC part with stockNumber==0 → stock field is None."""
    fx = _mock_fx(rate=0.14)
    svc = _lcsc_svc(fx=fx)
    products = [{"productCode": "C005", "productPriceList": [], "stockNumber": 0}]
    with patch("aiohttp.ClientSession", return_value=_lcsc_session(products)):
        results = await svc.search(None, "C005", 1)
    assert results[0].stock is None


# ---------------------------------------------------------------------------
# 18–20  FX in-memory cache TTL (fx.Fetcher)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fx_fetcher_cache_hit():
    """T-56-18  fx.Fetcher returns cached rate within TTL without hitting DB."""
    from kerf_cloud.fx import CachedRate, Fetcher

    pool = MagicMock()
    fetcher = Fetcher(cfg=MagicMock(cloud_fx_base_currency="USD", cloud_fx_settlement_currency="ZAR"), pool=pool)
    fetcher._cache["CNY/USD"] = CachedRate(
        rate=0.137,
        as_of=datetime.now(UTC),
        cached_at=datetime.now(UTC),  # fresh
    )

    rate, _, ok = await fetcher.rate("CNY", "USD")
    assert ok
    assert rate == pytest.approx(0.137)
    pool.acquire.assert_not_called()  # no DB call


@pytest.mark.asyncio
async def test_fx_fetcher_cache_miss_hits_db():
    """T-56-19  fx.Fetcher queries DB when cache is stale."""
    from kerf_cloud.fx import CachedRate, Fetcher

    stale_cached_at = datetime.now(UTC) - timedelta(seconds=200)
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={"rate": 0.13, "fetched_at": datetime.now(UTC)})
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))

    fetcher = Fetcher(cfg=MagicMock(), pool=pool)
    fetcher._cache["CNY/USD"] = CachedRate(rate=0.10, as_of=datetime.now(UTC), cached_at=stale_cached_at)

    rate, _, ok = await fetcher.rate("CNY", "USD")
    assert ok
    assert rate == pytest.approx(0.13)


@pytest.mark.asyncio
async def test_fx_fetcher_no_db_row_returns_false():
    """T-56-20  fx.Fetcher returns ok=False when no DB row exists."""
    from kerf_cloud.fx import Fetcher

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)))

    fetcher = Fetcher(cfg=MagicMock(), pool=pool)

    rate, _, ok = await fetcher.rate("CNY", "USD")
    assert not ok
    assert rate == 0.0


# ---------------------------------------------------------------------------
# 21–23  sync.refresh_part with mocked registry
# ---------------------------------------------------------------------------


def _fake_registry(provider: str, result: DistributorPart | None = None, raises: Exception | None = None):
    svc = AsyncMock()
    if raises:
        svc.lookup = AsyncMock(side_effect=raises)
        svc.search = AsyncMock(side_effect=raises)
    else:
        svc.lookup = AsyncMock(return_value=result)
        svc.search = AsyncMock(return_value=[result] if result else [])

    reg = MagicMock()
    reg.has = MagicMock(return_value=True)
    reg.acquire = AsyncMock(return_value=svc)
    reg.mark_used = AsyncMock()
    reg.enabled_names = MagicMock(return_value=[provider])
    return reg


@pytest.mark.asyncio
async def test_refresh_part_updates_price_and_stock():
    """T-56-21  refresh_part: successful lookup updates price_usd and stock."""
    result = DistributorPart(name=PROVIDER_DIGIKEY, sku="DK-R-001", price_usd=0.05, stock=9999)
    reg = _fake_registry(PROVIDER_DIGIKEY, result=result)

    doc = _part_doc([PROVIDER_DIGIKEY], fetched_at=_old_iso(30))
    new_json, n, _ = await refresh_part(None, reg, doc)
    assert n == 1
    updated = json.loads(new_json)
    dist = updated["distributors"][0]
    assert dist["price_usd"] == pytest.approx(0.05)
    assert dist["stock"] == 9999


@pytest.mark.asyncio
async def test_refresh_part_lookup_exception_skips_entry():
    """T-56-22  refresh_part: lookup exception logs warning but returns original JSON."""
    reg = _fake_registry(PROVIDER_DIGIKEY, raises=Exception("upstream error"))

    doc = _part_doc([PROVIDER_DIGIKEY], fetched_at=_old_iso(30))
    new_json, n, _ = await refresh_part(None, reg, doc)
    assert n == 0
    assert new_json == doc  # unchanged


@pytest.mark.asyncio
async def test_refresh_part_no_distributors_returns_unchanged():
    """T-56-23  refresh_part: no distributors in doc → no updates."""
    reg = MagicMock()
    doc = json.dumps({"name": "bare-part"})
    new_json, n, _ = await refresh_part(None, reg, doc)
    assert n == 0
    assert new_json == doc


# ---------------------------------------------------------------------------
# 24–25  Staleness-driven refresh round-trips (combined is_stale + refresh_part)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stale_part_gets_refreshed_fresh_part_skipped():
    """T-56-24  Stale doc is updated; fresh doc is not, confirming TTL logic."""
    fresh_result = DistributorPart(name=PROVIDER_MOUSER, sku="MO-IC-001", price_usd=1.23, stock=500)
    reg = _fake_registry(PROVIDER_MOUSER, result=fresh_result)

    stale_doc = _part_doc([PROVIDER_MOUSER], fetched_at=_old_iso(30))
    fresh_doc = _part_doc([PROVIDER_MOUSER], fetched_at=_now_iso())

    assert is_stale(stale_doc)
    assert not is_stale(fresh_doc)

    new_json, n, _ = await refresh_part(None, reg, stale_doc)
    assert n == 1
    assert json.loads(new_json)["distributors"][0]["price_usd"] == pytest.approx(1.23)

    # Fresh doc: refresh_part still runs but the registry returns a good result
    # (TTL enforcement is caller responsibility; here we just confirm n==1 for stale)


@pytest.mark.asyncio
async def test_multi_distributor_partial_refresh():
    """T-56-25  Part with DigiKey + LCSC: registry only has DigiKey; LCSC skipped."""
    dk_result = DistributorPart(name=PROVIDER_DIGIKEY, sku="DK-IC-777", price_usd=2.50, stock=200)

    svc = AsyncMock()
    svc.lookup = AsyncMock(return_value=dk_result)

    reg = MagicMock()

    def _has(name):
        return name == PROVIDER_DIGIKEY

    reg.has = MagicMock(side_effect=_has)
    reg.acquire = AsyncMock(return_value=svc)
    reg.mark_used = AsyncMock()

    doc = _part_doc([PROVIDER_DIGIKEY, PROVIDER_LCSC], fetched_at=_old_iso(30))
    new_json, n, _ = await refresh_part(None, reg, doc)

    # Only DigiKey was in registry → only 1 update
    assert n == 1
    updated = json.loads(new_json)
    dk_entry = next(e for e in updated["distributors"] if e["name"] == PROVIDER_DIGIKEY)
    lcsc_entry = next(e for e in updated["distributors"] if e["name"] == PROVIDER_LCSC)
    assert dk_entry["price_usd"] == pytest.approx(2.50)
    assert "price_usd" not in lcsc_entry
