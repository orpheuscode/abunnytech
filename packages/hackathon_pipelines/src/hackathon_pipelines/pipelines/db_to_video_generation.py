"""DB-backed bridge from analyzed reels to Gemini prompting and Veo generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from hackathon_pipelines.contracts import (
    GeneratedVideoArtifact,
    GenerationBundle,
    ProductCandidate,
    ReelSurfaceMetrics,
    TemplateDisposition,
    VideoTemplateRecord,
)
from hackathon_pipelines.pipelines.video_generation import VideoGenerationPipeline
from hackathon_pipelines.ports import GeminiVideoAgentPort, VeoGeneratorPort
from hackathon_pipelines.stores.memory import new_id
from hackathon_pipelines.stores.sqlite_store import SQLiteHackathonStore


@dataclass(frozen=True)
class DatabaseVideoGenerationResult:
    """Result bundle for DB-driven Gemini/Veo generation."""

    template: VideoTemplateRecord
    product: ProductCandidate
    bundle: GenerationBundle
    artifact: GeneratedVideoArtifact
    templates_created: int


def _template_score(store: SQLiteHackathonStore, template: VideoTemplateRecord) -> tuple[int, int, int, datetime, str]:
    structure = store.get_structure(template.structure_record_id)
    metric: ReelSurfaceMetrics | None = None
    if structure is not None:
        metric = store.get_reel_metric(structure.source_reel_id)
    return (
        metric.likes if metric is not None else -1,
        metric.comments if metric is not None else -1,
        metric.views if metric is not None else -1,
        template.updated_at or template.created_at or datetime.min.replace(tzinfo=UTC),
        template.template_id,
    )


async def ensure_templates_from_structures(
    store: SQLiteHackathonStore,
    *,
    gemini: GeminiVideoAgentPort,
) -> list[VideoTemplateRecord]:
    """Create missing templates for structures already stored in SQLite."""

    templates = list(store.list_templates())
    existing_structure_ids = {template.structure_record_id for template in templates}
    created: list[VideoTemplateRecord] = []
    for structure in store.list_structures():
        if structure.record_id in existing_structure_ids:
            continue
        disposition, reason, veo_prompt = await gemini.decide_template_disposition(
            structure,
            peer_templates=templates,
        )
        if disposition == TemplateDisposition.DISCARD:
            continue
        template = VideoTemplateRecord(
            template_id=new_id("tpl"),
            structure_record_id=structure.record_id,
            veo_prompt_draft=veo_prompt,
            disposition=disposition,
            disposition_reason=reason,
        )
        store.save_template(template)
        templates.append(template)
        created.append(template)
    return created


def pick_best_template(store: SQLiteHackathonStore) -> VideoTemplateRecord:
    """Pick the strongest saved template using source-reel engagement as the primary signal."""

    templates = store.list_templates()
    if not templates:
        msg = "No video templates exist in the database."
        raise RuntimeError(msg)
    return max(templates, key=lambda template: _template_score(store, template))


def build_test_product_candidate(
    *,
    product_image_path: str,
    title: str | None = None,
    description: str | None = None,
) -> ProductCandidate:
    """Create a simple product candidate for manual generation from a local asset."""

    path = Path(product_image_path)
    resolved_title = (title or path.stem.replace("_", " ").replace("-", " ").strip() or "Demo Product").title()
    notes = description or (
        f"Use the reference product image at {path.name} as the source of truth. "
        "Keep the commercial simple, creator-style, and visually direct."
    )
    return ProductCandidate(
        product_id=f"manual_{path.stem or 'product'}",
        title=resolved_title,
        source_url=f"file://{path.resolve()}",
        platform="manual_asset",
        visual_marketability=0.9,
        popularity_signal=0.6,
        content_potential=0.85,
        dropship_score=0.8,
        notes=notes,
    )


async def generate_video_from_best_db_template(
    store: SQLiteHackathonStore,
    *,
    gemini: GeminiVideoAgentPort,
    veo: VeoGeneratorPort,
    product_image_path: str,
    avatar_image_path: str,
    product_title: str | None = None,
    product_description: str | None = None,
) -> DatabaseVideoGenerationResult:
    """Ensure templates exist, pick the best one, then run Gemini -> Veo generation."""

    existing_templates = store.list_templates()
    created_templates: list[VideoTemplateRecord]
    if existing_templates:
        created_templates = []
    else:
        created_templates = await ensure_templates_from_structures(store, gemini=gemini)
    template = pick_best_template(store)
    product = build_test_product_candidate(
        product_image_path=product_image_path,
        title=product_title,
        description=product_description,
    )
    pipeline = VideoGenerationPipeline(gemini=gemini, veo=veo)
    bundle, artifact = await pipeline.generate_for_product(
        template,
        product,
        product_image_path=product_image_path,
        avatar_image_path=avatar_image_path,
    )
    return DatabaseVideoGenerationResult(
        template=template,
        product=product,
        bundle=bundle,
        artifact=artifact,
        templates_created=len(created_templates),
    )
