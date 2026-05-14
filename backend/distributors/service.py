from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import aiohttp


PROVIDER_DIGIKEY = "digikey"
PROVIDER_MOUSER = "mouser"
PROVIDER_LCSC = "lcsc"
PROVIDER_MCMASTER = "mcmaster"

ALL_PROVIDERS = [PROVIDER_DIGIKEY, PROVIDER_MOUSER, PROVIDER_LCSC, PROVIDER_MCMASTER]


@dataclass
class Credentials:
    client_id: str = ""
    client_secret: str = ""
    api_key: str = ""


@dataclass
class DistributorPart:
    name: str
    sku: str = ""
    url: str = ""
    price_usd: Optional[float] = None
    stock: Optional[int] = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw: Optional[dict] = None


class DistributorNotFound(Exception):
    pass


class DistributorNotSupported(Exception):
    pass


class DistributorAuthError(Exception):
    pass


class DistributorRateLimitError(Exception):
    pass


class DistributorNotConfigured(Exception):
    pass


class Service(ABC):
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def lookup(self, ctx, sku: str) -> DistributorPart:
        raise NotImplementedError

    @abstractmethod
    async def search(self, ctx, query: str, limit: int) -> list[DistributorPart]:
        raise NotImplementedError


def validate_credentials(name: str, creds: Credentials) -> None:
    if name == PROVIDER_DIGIKEY:
        if not creds.client_id or not creds.client_secret:
            raise ValueError("digikey requires client_id and client_secret")
    elif name in (PROVIDER_MOUSER, PROVIDER_LCSC):
        if not creds.api_key:
            raise ValueError(f"{name} requires api_key")
    elif name == PROVIDER_MCMASTER:
        pass
    else:
        raise ValueError(f"unknown distributor: {name}")
