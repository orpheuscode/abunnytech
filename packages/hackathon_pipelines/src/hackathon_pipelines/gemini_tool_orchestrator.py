"""Gemini-driven meta-orchestration: the model chooses and runs hackathon pipelines via function calls."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types as genai_types

from hackathon_pipelines.orchestrator import HackathonOrchestrator

_META_SYSTEM = """You are the control plane for an autonomous UGC video pipeline.
You must accomplish the user's goal by calling the provided tools. Each tool runs a real pipeline stage
(reel discovery → templates, product-ranked video generation, or publish + analytics feedback).
Call tools in a sensible order. When the goal is satisfied, reply with a short plain-text summary of what
ran and key outcomes.
Do not invent tool results; always use the tools."""


def _pipeline_tool_declarations() -> genai_types.Tool:
    empty_object = genai_types.Schema(type=genai_types.Type.OBJECT, properties={})
    return genai_types.Tool(
        function_declarations=[
            genai_types.FunctionDeclaration(
                name="run_reel_to_template_cycle",
                description=(
                    "Run reel discovery: browser scroll → download → video understanding → "
                    "Gemini template decision → persist templates. Use first to build templates."
                ),
                parameters=empty_object,
            ),
            genai_types.FunctionDeclaration(
                name="run_product_to_video",
                description=(
                    "Rank products for a niche, ensure templates exist, then Gemini+Veo-shaped generation "
                    "for the top product using the given image paths."
                ),
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "product_image_path": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Filesystem path to product reference image.",
                        ),
                        "avatar_image_path": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Filesystem path to avatar / creator reference image.",
                        ),
                        "niche_query": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Product discovery query (e.g. dropship niche).",
                        ),
                    },
                    required=["product_image_path", "avatar_image_path"],
                ),
            ),
            genai_types.FunctionDeclaration(
                name="run_publish_and_feedback",
                description=(
                    "Publish a reel (dry-run by default), fetch analytics, and update template performance labels."
                ),
                parameters=genai_types.Schema(
                    type=genai_types.Type.OBJECT,
                    properties={
                        "media_path": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Path to video file to post.",
                        ),
                        "caption": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Post caption.",
                        ),
                        "template_id": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Existing template_id from the template store.",
                        ),
                        "dry_run": genai_types.Schema(
                            type=genai_types.Type.BOOLEAN,
                            description="If true, skip real browser post (default true).",
                        ),
                    },
                    required=["media_path", "caption", "template_id"],
                ),
            ),
        ]
    )


async def dispatch_pipeline_tool(
    orchestrator: HackathonOrchestrator,
    *,
    name: str,
    args: dict[str, Any] | None,
) -> dict[str, Any]:
    """Execute one orchestrator method by tool name; returns JSON-serializable payload for the model."""
    raw = args or {}
    try:
        if name == "run_reel_to_template_cycle":
            summary = await orchestrator.run_reel_to_template_cycle()
        elif name == "run_product_to_video":
            summary = await orchestrator.run_product_to_video(
                product_image_path=str(raw["product_image_path"]),
                avatar_image_path=str(raw["avatar_image_path"]),
                niche_query=str(raw.get("niche_query") or "dropship"),
            )
        elif name == "run_publish_and_feedback":
            summary = await orchestrator.run_publish_and_feedback(
                media_path=str(raw["media_path"]),
                caption=str(raw["caption"]),
                template_id=str(raw["template_id"]),
                dry_run=bool(raw.get("dry_run", True)),
            )
        else:
            return {"ok": False, "error": f"unknown_tool:{name}"}
    except KeyError as e:
        return {"ok": False, "error": f"missing_parameter:{e.args[0]}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {"ok": True, "summary": summary.model_dump(mode="json")}


def _iter_function_calls(parts: list[genai_types.Part] | None) -> list[genai_types.FunctionCall]:
    if not parts:
        return []
    out: list[genai_types.FunctionCall] = []
    for p in parts:
        if p.function_call is not None:
            out.append(p.function_call)
    return out


def _response_text(resp: genai_types.GenerateContentResponse) -> str | None:
    text = getattr(resp, "text", None)
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None


@dataclass
class GeminiOrchestrationResult:
    """Trace of a Gemini tool-orchestrated session."""

    final_text: str | None
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    turns_used: int = 0


async def run_gemini_pipeline_orchestration(
    orchestrator: HackathonOrchestrator,
    *,
    instruction: str,
    api_key: str | None = None,
    model: str | None = None,
    max_turns: int = 12,
) -> GeminiOrchestrationResult:
    """
    Let Gemini decide which pipelines to run by issuing function calls; each call executes the real
    `HackathonOrchestrator` method on the injected stack.

    Requires ``GOOGLE_API_KEY`` or ``GEMINI_API_KEY`` (or pass ``api_key``). Raises if missing.
    """
    key = (api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or "").strip()
    if not key:
        msg = "GOOGLE_API_KEY or GEMINI_API_KEY is required for Gemini meta-orchestration"
        raise RuntimeError(msg)

    resolved_model = model or os.getenv("GEMINI_META_ORCHESTRATION_MODEL") or os.getenv(
        "GEMINI_ORCHESTRATION_MODEL", "gemini-2.5-flash"
    )
    client = genai.Client(api_key=key)
    tools = _pipeline_tool_declarations()
    config = genai_types.GenerateContentConfig(
        tools=[tools],
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
    )

    # First turn bundles system rules with the task (stable across Gemini API variants).
    contents: list[genai_types.Content] = [
        genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=f"{_META_SYSTEM}\n\n---\n\nUser task:\n{instruction}")],
        ),
    ]
    trace: list[dict[str, Any]] = []
    turns = 0
    final_text: str | None = None

    while turns < max_turns:
        turns += 1
        resp = await client.aio.models.generate_content(
            model=resolved_model,
            contents=contents,
            config=config,
        )
        cands = resp.candidates or []
        if not cands or not cands[0].content:
            break
        mc = cands[0].content
        parts = list(mc.parts or [])
        role = mc.role or "model"
        contents.append(genai_types.Content(role=role, parts=parts))
        calls = _iter_function_calls(parts)

        if not calls:
            final_text = _response_text(resp)
            break

        response_parts: list[genai_types.Part] = []
        for fc in calls:
            fname = fc.name or ""
            fargs = dict(fc.args or {})
            payload = await dispatch_pipeline_tool(orchestrator, name=fname, args=fargs)
            trace.append({"name": fname, "args": fargs, "result": payload})
            fr = genai_types.FunctionResponse(
                name=fname,
                id=fc.id,
                response=payload,
            )
            response_parts.append(genai_types.Part(function_response=fr))

        contents.append(genai_types.Content(role="user", parts=response_parts))

    return GeminiOrchestrationResult(final_text=final_text, tool_trace=trace, turns_used=turns)
