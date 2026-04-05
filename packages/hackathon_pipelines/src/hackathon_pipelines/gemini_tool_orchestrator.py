"""Gemini-driven meta-orchestration: the model chooses and runs hackathon pipelines via function calls."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from google import genai
from google.genai import types as genai_types

from hackathon_pipelines.orchestrator import HackathonOrchestrator

_META_SYSTEM = """You are the control plane for an autonomous UGC storefront pipeline.
Your job is to complete the user's goal by calling the provided tools until the workflow is done.

PIPELINE CAPABILITIES:
- run_reel_to_template_cycle:
  Browser-led reel discovery -> download/analysis -> Gemini template selection -> template persistence.
- run_product_to_video:
  Product ranking for the requested niche -> ensure templates exist -> Gemini/Veo-style video generation
  using the provided product and avatar assets.
- run_publish_and_feedback:
  Publish an existing media file, fetch analytics, and update template performance labels.
  In live mode, a successful publish also triggers Instagram comment engagement automatically.
- run_closed_loop_cycle:
  Full end-to-end loop in one call:
  discovery -> template creation -> product ranking -> video generation -> publish ->
  comment engagement in live mode -> analytics feedback.

OPERATING RULES:
1. Prefer run_closed_loop_cycle when the user wants the whole pipeline, end-to-end storefront execution,
   posting plus comment handling, or anything close to "do everything".
2. Prefer narrower tools only when the user clearly asks for a partial workflow or when you already have
   the required artifact/template context from earlier tool calls.
3. Reuse the exact parameter values provided in the user task block. Do not rewrite file paths, caption
   text, dry_run, or other supplied arguments unless the user explicitly asks.
4. If a tool returns an error or missing context, adapt by calling the next sensible tool; do not invent
   successful results.
5. Keep the number of tool calls minimal while still satisfying the goal.
6. Never invent tool outputs, post URLs, IDs, analytics, or engagement results. Only report what tools return.
7. When the goal is satisfied, reply with a short plain-text summary covering what ran, major outcomes,
   and whether publishing, comment engagement, and analytics feedback happened.
"""


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
                    "Publish a reel (dry-run by default), fetch analytics, update template performance labels, "
                    "and in live mode automatically engage post comments after a successful publish."
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
            genai_types.FunctionDeclaration(
                name="run_closed_loop_cycle",
                description=(
                    "Run the full storefront loop end to end: reel discovery, template creation, product ranking, "
                    "video generation, publish, comment engagement in live mode, and analytics feedback."
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
                        "caption": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Caption to use for the generated post.",
                        ),
                        "media_path": genai_types.Schema(
                            type=genai_types.Type.STRING,
                            description="Optional path for the publishable video artifact.",
                        ),
                        "dry_run": genai_types.Schema(
                            type=genai_types.Type.BOOLEAN,
                            description="If true, simulate publish/comment actions instead of using the real browser.",
                        ),
                    },
                    required=["product_image_path", "avatar_image_path"],
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
        elif name == "run_closed_loop_cycle":
            summary = await orchestrator.run_closed_loop_cycle(
                product_image_path=str(raw["product_image_path"]),
                avatar_image_path=str(raw["avatar_image_path"]),
                niche_query=str(raw.get("niche_query") or "dropship"),
                caption=str(raw.get("caption") or "Auto-generated UGC"),
                media_path=str(raw["media_path"]) if raw.get("media_path") else None,
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
