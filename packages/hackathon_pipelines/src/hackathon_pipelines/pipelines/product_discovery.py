"""Product discovery: Browser Use on AliExpress / trend surfaces → scored catalog."""

from __future__ import annotations

import json
import uuid

from browser_runtime.types import AgentResult, AgentTask

from hackathon_pipelines.contracts import ProductCandidate
from hackathon_pipelines.ports import BrowserAutomationPort, ProductCatalogPort


def _parse_products(result: AgentResult) -> list[ProductCandidate]:
    out = result.output
    raw = out.get("products_json") or out.get("products")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if not isinstance(raw, list):
        return []
    out_list: list[ProductCandidate] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("product_id") or f"prod_{uuid.uuid4().hex[:8]}")
        out_list.append(
            ProductCandidate(
                product_id=pid,
                title=str(item.get("title", "unknown")),
                source_url=str(item.get("source_url", "https://example.invalid")),
                platform=str(item.get("platform", "aliexpress")),
                visual_marketability=float(item.get("visual_marketability", 0.5)),
                popularity_signal=float(item.get("popularity_signal", 0.5)),
                content_potential=float(item.get("content_potential", 0.5)),
                dropship_score=float(item.get("dropship_score", 0.5)),
                notes=item.get("notes"),
            )
        )
    return out_list


class ProductDiscoveryPipeline:
    def __init__(self, *, browser: BrowserAutomationPort, catalog: ProductCatalogPort) -> None:
        self._browser = browser
        self._catalog = catalog

    async def discover_and_rank(
        self,
        *,
        niche_query: str = "portable gadgets",
        top_n: int = 5,
    ) -> list[ProductCandidate]:
        task = AgentTask(
            description=(
                f"Browse AliExpress (or similar) for: {niche_query}. Extract candidate products with "
                "title, url, and subjective scores 0-1 for visual_marketability, popularity_signal, "
                "content_potential, dropship_score (overall dropship fit). "
                'Return JSON only: {"products":[{"product_id":"...","title":"...","source_url":"...",'
                '"platform":"aliexpress","visual_marketability":0.7,"popularity_signal":0.6,'
                '"content_potential":0.8,"dropship_score":0.65,"notes":"..."}]}'
            ),
            max_steps=30,
            metadata={"niche": niche_query},
        )
        result = await self._browser.run_task(task)
        found = _parse_products(result)
        if not found and result.dry_run:
            found = [
                ProductCandidate(
                    product_id=f"dry_{uuid.uuid4().hex[:8]}",
                    title=f"Dry-run {niche_query}",
                    source_url="https://www.aliexpress.com/dry_run",
                    dropship_score=0.9,
                    visual_marketability=0.85,
                    popularity_signal=0.7,
                    content_potential=0.88,
                )
            ]
        self._catalog.upsert_candidates(found)
        return self._catalog.top_by_score(limit=top_n)
