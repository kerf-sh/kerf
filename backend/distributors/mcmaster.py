from distributors.service import (
    PROVIDER_MCMASTER,
    DistributorNotSupported,
    DistributorPart,
    Service,
)


class McMasterService(Service):
    def name(self) -> str:
        return PROVIDER_MCMASTER

    async def lookup(self, ctx, sku: str) -> DistributorPart:
        raise DistributorNotSupported("mcmaster: no public API available")

    async def search(self, ctx, query: str, limit: int) -> list[DistributorPart]:
        raise DistributorNotSupported("mcmaster: no public API available")
