from __future__ import annotations

import pytest

from hackathon_pipelines import build_dry_run_stack, dispatch_pipeline_tool
from hackathon_pipelines.gemini_tool_orchestrator import _pipeline_tool_declarations


@pytest.mark.asyncio
async def test_dispatch_reel_cycle() -> None:
    stack = build_dry_run_stack()
    out = await dispatch_pipeline_tool(stack.orchestrator, name="run_reel_to_template_cycle", args={})
    assert out["ok"] is True
    assert out["summary"]["templates_created"] >= 1


@pytest.mark.asyncio
async def test_dispatch_product_to_video(tmp_path) -> None:
    stack = build_dry_run_stack()
    p = tmp_path / "p.png"
    p.write_bytes(b"x")
    a = tmp_path / "a.png"
    a.write_bytes(b"y")
    out = await dispatch_pipeline_tool(
        stack.orchestrator,
        name="run_product_to_video",
        args={"product_image_path": str(p), "avatar_image_path": str(a), "niche_query": "gadgets"},
    )
    assert out["ok"] is True
    assert out["summary"]["generations"] == 1


@pytest.mark.asyncio
async def test_dispatch_publish_requires_template(tmp_path) -> None:
    stack = build_dry_run_stack()
    await dispatch_pipeline_tool(stack.orchestrator, name="run_reel_to_template_cycle", args={})
    tpl = stack.templates.list_templates()[0]
    v = tmp_path / "v.mp4"
    v.write_bytes(b"")
    out = await dispatch_pipeline_tool(
        stack.orchestrator,
        name="run_publish_and_feedback",
        args={"media_path": str(v), "caption": "hi", "template_id": tpl.template_id, "dry_run": True},
    )
    assert out["ok"] is True
    assert out["summary"]["posts"] == 1


@pytest.mark.asyncio
async def test_dispatch_closed_loop_cycle(tmp_path) -> None:
    stack = build_dry_run_stack()
    p = tmp_path / "product.png"
    p.write_bytes(b"x")
    a = tmp_path / "avatar.png"
    a.write_bytes(b"y")
    m = tmp_path / "generated.mp4"
    out = await dispatch_pipeline_tool(
        stack.orchestrator,
        name="run_closed_loop_cycle",
        args={
            "product_image_path": str(p),
            "avatar_image_path": str(a),
            "niche_query": "beauty gadgets",
            "caption": "launching now",
            "media_path": str(m),
            "dry_run": True,
        },
    )
    assert out["ok"] is True
    assert out["summary"]["product_summary"]["generations"] == 1
    assert out["summary"]["publish_summary"]["posts"] == 1


def test_pipeline_tool_declarations_include_closed_loop() -> None:
    tool = _pipeline_tool_declarations()
    names = [decl.name for decl in tool.function_declarations or []]
    assert "run_closed_loop_cycle" in names


@pytest.mark.asyncio
async def test_dispatch_unknown_tool() -> None:
    stack = build_dry_run_stack()
    out = await dispatch_pipeline_tool(stack.orchestrator, name="nope", args={})
    assert out["ok"] is False
