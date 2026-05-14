import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import aiohttp

from distributors.service import (
    ALL_PROVIDERS,
    PROVIDER_DIGIKEY,
    PROVIDER_LCSC,
    PROVIDER_MOUSER,
    PROVIDER_MCMASTER,
    Credentials,
    DistributorNotConfigured,
    Service,
    validate_credentials,
)

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 10.0

from kerf_core.utils.encrypt import decrypt_secret, encrypt_secret

SECRET_DOMAIN = "distributor-credentials"


@dataclass
class ServiceMeta:
    name: str
    enabled: bool
    rate_limit_per_minute: int
    last_used_at: Optional[datetime]
    has_secret: bool
    updated_at: Optional[datetime] = None


class Registry:
    def __init__(self, pool, cfg, fx=None):
        self._pool = pool
        self._cfg = cfg
        self._fx = fx
        self._services: dict[str, Service] = {}
        self._limiters: dict[str, dict] = {}
        self._meta: dict[str, ServiceMeta] = {}
        self._lock = asyncio.Lock()
        self._http_timeout = aiohttp.ClientTimeout(total=HTTP_TIMEOUT)

    async def reload(self) -> None:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select name, enabled, secret_encrypted, rate_limit_per_minute, last_used_at, updated_at
                from distributor_credentials
                """
            )

        next_services: dict[str, Service] = {}
        next_limiters: dict[str, dict] = {}
        next_meta: dict[str, ServiceMeta] = {}

        for row in rows:
            name = row["name"]
            enabled = row["enabled"]
            ciphertext = row["secret_encrypted"]
            limit = row["rate_limit_per_minute"]
            last_used = row["last_used_at"]
            updated_at = row["updated_at"]

            next_meta[name] = ServiceMeta(
                name=name,
                enabled=enabled,
                rate_limit_per_minute=limit,
                last_used_at=last_used,
                has_secret=len(ciphertext) > 0 if ciphertext else False,
                updated_at=updated_at,
            )

            if not enabled or not ciphertext:
                continue

            try:
                plaintext = decrypt_secret(ciphertext, SECRET_DOMAIN)
            except Exception as e:
                logger.warning(f"distributors: decrypt {name}: {e} (skipping; will need re-entry)")
                continue

            try:
                creds_dict = json.loads(plaintext)
                creds = Credentials(
                    client_id=creds_dict.get("client_id", ""),
                    client_secret=creds_dict.get("client_secret", ""),
                    api_key=creds_dict.get("api_key", ""),
                )
            except json.JSONDecodeError as e:
                logger.warning(f"distributors: parse credentials {name}: {e} (skipping)")
                continue

            try:
                svc = self._build_service(name, creds)
            except Exception as e:
                logger.warning(f"distributors: build service {name}: {e} (skipping)")
                continue

            next_services[name] = svc

            per_min = limit if limit > 0 else 60
            per_sec = per_min / 60.0
            if per_sec <= 0:
                per_sec = 1
            burst = max(1, per_min // 4)
            next_limiters[name] = {
                "limiter": asyncio.Semaphore(1),
                "rate": per_sec,
                "burst": burst,
                "last_call": 0.0,
                "call_count": 0,
            }

        async with self._lock:
            self._services = next_services
            self._limiters = next_limiters
            self._meta = next_meta

    def _build_service(self, name: str, creds: Credentials) -> Service:
        if name == PROVIDER_DIGIKEY:
            from distributors.digikey import DigiKeyService

            return DigiKeyService(creds, self._http_timeout.total)
        elif name == PROVIDER_MOUSER:
            from distributors.mouser import MouserService

            return MouserService(creds, self._http_timeout.total)
        elif name == PROVIDER_LCSC:
            from distributors.lcsc import LCSCService

            return LCSCService(creds, self._http_timeout.total, self._fx)
        elif name == PROVIDER_MCMASTER:
            from distributors.mcmaster import McMasterService

            return McMasterService()
        else:
            raise ValueError(f"unknown distributor: {name}")

    async def acquire(self, name: str) -> Service:
        async with self._lock:
            svc = self._services.get(name)
            limiter = self._limiters.get(name)

        if not svc:
            raise DistributorNotConfigured(f"distributor {name} not configured or disabled")

        if limiter:
            now = time.time()
            async with self._lock:
                last_call = limiter.get("last_call", 0)
                call_count = limiter.get("call_count", 0)

                if now - last_call < 1.0:
                    if call_count >= limiter["burst"]:
                        sleep_time = 1.0 - (now - last_call)
                        if sleep_time > 0:
                            await asyncio.sleep(sleep_time)
                        now = time.time()
                        call_count = 0
                else:
                    call_count = 0

                limiter["last_call"] = now
                limiter["call_count"] = call_count + 1

        return svc

    def has(self, name: str) -> bool:
        return name in self._services

    async def mark_used(self, name: str) -> None:
        if not self._pool:
            return
        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    "update distributor_credentials set last_used_at = now(), updated_at = now() where name = $1",
                    name,
                )
        except Exception as e:
            logger.warning(f"distributors: mark-used {name}: {e}")

    def meta(self) -> list[ServiceMeta]:
        result: list[ServiceMeta] = []
        seen: set[str] = set()

        for name in ALL_PROVIDERS:
            if name in self._meta:
                result.append(self._meta[name])
            else:
                result.append(
                    ServiceMeta(
                        name=name,
                        enabled=False,
                        rate_limit_per_minute=60,
                        last_used_at=None,
                        has_secret=False,
                    )
                )
            seen.add(name)

        for name, m in self._meta.items():
            if name not in seen:
                result.append(m)

        return result

    async def upsert(
        self, name: str, enabled: bool, rate_limit_per_minute: int, creds: Credentials
    ) -> ServiceMeta:
        validate_credentials(name, creds)

        if rate_limit_per_minute <= 0:
            rate_limit_per_minute = 60

        plain = json.dumps(
            {
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "api_key": creds.api_key,
            }
        )

        enc = encrypt_secret(plain.encode(), SECRET_DOMAIN)

        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                insert into distributor_credentials (name, enabled, secret_encrypted, rate_limit_per_minute)
                values ($1, $2, $3, $4)
                on conflict (name) do update set
                    enabled = excluded.enabled,
                    secret_encrypted = excluded.secret_encrypted,
                    rate_limit_per_minute = excluded.rate_limit_per_minute,
                    updated_at = now()
                returning updated_at, last_used_at
                """,
                name,
                enabled,
                enc,
                rate_limit_per_minute,
            )

        await self.reload()

        return ServiceMeta(
            name=name,
            enabled=enabled,
            rate_limit_per_minute=rate_limit_per_minute,
            last_used_at=row["last_used_at"] if row else None,
            has_secret=True,
            updated_at=row["updated_at"] if row else None,
        )

    async def delete(self, name: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute("delete from distributor_credentials where name = $1", name)
        await self.reload()

    def set_fx(self, fx) -> None:
        self._fx = fx

    def enabled_names(self) -> list[str]:
        return list(self._services.keys())


_dist_registry: Optional[Registry] = None


def get_registry() -> Optional[Registry]:
    return _dist_registry


def set_registry(r: Registry) -> None:
    global _dist_registry
    _dist_registry = r
