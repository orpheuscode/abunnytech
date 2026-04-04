"""
Shopify admin adapter (Stage 5 — Monetize).

Live path:  Shopify Admin REST API via PlatformAPIProvider
Demo/test:  MockProvider

Credential env vars:
  SHOPIFY_STORE_DOMAIN    — e.g. mystore.myshopify.com
  SHOPIFY_ADMIN_TOKEN     — Admin API access token
  SHOPIFY_API_VERSION     — e.g. 2024-01 (default)

Note: Shopify operations are behind the stage5_monetize feature flag.
Callers should check the flag before constructing this adapter.
"""
from __future__ import annotations

import os

from ..audit import AuditLogger
from ..providers.base import BrowserProvider
from ..providers.mock import MockProvider
from ..types import (
    AnalyticsData,
    AnalyticsFetchRequest,
    CommentReplyRequest,
    CommentReplyResult,
    DMRequest,
    DMResult,
    Platform,
    PlatformAPIRequest,
    PostContentRequest,
    PostContentResult,
    TrendingFetchRequest,
    TrendingItem,
)
from .base import PlatformAdapter

_DEFAULT_API_VERSION = "2024-01"


class ShopifyAdapter(PlatformAdapter):
    """
    Shopify admin operations: product management, order data, discount creation.

    post_content / reply_to_comment / send_dm are not applicable to Shopify;
    they raise NotImplementedError to make misuse obvious.

    Use fetch_analytics for revenue/order metrics.
    """

    def __init__(self, provider: BrowserProvider, audit: AuditLogger | None = None) -> None:
        super().__init__(provider, audit)
        self._store_domain = os.getenv("SHOPIFY_STORE_DOMAIN", "")
        self._api_version = os.getenv("SHOPIFY_API_VERSION", _DEFAULT_API_VERSION)

    @property
    def platform(self) -> Platform:
        return Platform.SHOPIFY

    def _api_endpoint(self, path: str) -> str:
        """Build a Shopify Admin API endpoint path."""
        return f"/admin/api/{self._api_version}/{path.lstrip('/')}"

    async def post_content(self, request: PostContentRequest) -> PostContentResult:
        raise NotImplementedError(
            "ShopifyAdapter does not support post_content. Use TikTokAdapter or InstagramAdapter."
        )

    async def reply_to_comment(self, request: CommentReplyRequest) -> CommentReplyResult:
        raise NotImplementedError("ShopifyAdapter does not support comment replies.")

    async def send_dm(self, request: DMRequest) -> DMResult:
        raise NotImplementedError("ShopifyAdapter does not support DMs.")

    async def fetch_analytics(self, request: AnalyticsFetchRequest) -> AnalyticsData:
        """Fetch order/revenue metrics from Shopify as AnalyticsData."""
        self._check_kill_switch()

        if isinstance(self._provider, MockProvider):
            return await self._provider.fetch_analytics(request)

        params: dict = {"status": "any", "limit": 250}
        if request.since:
            params["created_at_min"] = request.since.isoformat()
        if request.until:
            params["created_at_max"] = request.until.isoformat()

        api_request = PlatformAPIRequest(
            platform=Platform.SHOPIFY,
            method="GET",
            endpoint=self._api_endpoint("/orders.json"),
            params=params,
        )
        api_response = await self._provider.call_platform_api(api_request)
        orders = api_response.data.get("orders", [])
        revenue = sum(float(o.get("total_price", 0)) for o in orders)

        return AnalyticsData(
            request_id=request.request_id,
            platform=Platform.SHOPIFY,
            views=len(orders),   # re-purposed: order count
            # revenue isn't in AnalyticsData — store in saves field for now
            # TODO: propose revenue_usd field addition to AnalyticsData contract
            saves=int(revenue * 100),  # cents, avoids float in int field
        )

    async def fetch_trending(self, request: TrendingFetchRequest) -> list[TrendingItem]:
        raise NotImplementedError("ShopifyAdapter does not support trending fetch.")

    # ------------------------------------------------------------------
    # Shopify-specific helpers for Stage 5 consumers
    # ------------------------------------------------------------------

    async def create_discount(
        self,
        title: str,
        code: str,
        percentage: float,
        usage_limit: int = 100,
        dry_run: bool = True,
    ) -> dict:
        """Create a percentage discount code in Shopify."""
        self._check_kill_switch()
        req = PlatformAPIRequest(
            platform=Platform.SHOPIFY,
            method="POST",
            endpoint=self._api_endpoint("/price_rules.json"),
            body={
                "price_rule": {
                    "title": title,
                    "target_type": "line_item",
                    "target_selection": "all",
                    "allocation_method": "across",
                    "value_type": "percentage",
                    "value": f"-{percentage}",
                    "customer_selection": "all",
                    "usage_limit": usage_limit,
                    "starts_at": "2024-01-01T00:00:00Z",
                }
            },
            dry_run=dry_run,
        )
        resp = await self._provider.call_platform_api(req)
        self._audit.log("shopify.create_discount", {"title": title, "code": code, "dry_run": dry_run})
        return resp.data

    async def list_products(self, limit: int = 50, dry_run: bool = True) -> list[dict]:
        """Return product listings from the Shopify store."""
        self._check_kill_switch()
        req = PlatformAPIRequest(
            platform=Platform.SHOPIFY,
            method="GET",
            endpoint=self._api_endpoint("/products.json"),
            params={"limit": limit},
            dry_run=dry_run,
        )
        resp = await self._provider.call_platform_api(req)
        return resp.data.get("products", [])
