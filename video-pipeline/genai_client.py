"""Create a google-genai Client for Gemini Developer API or Vertex AI."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai


def create_genai_client(script_dir: Path) -> genai.Client:
    """
    Gemini Developer API (default):
      GEMINI_API_KEY=...

    Vertex AI — pick one:

    A) API key (Vertex “express” / console key):
      GOOGLE_GENAI_USE_VERTEXAI=true
      GEMINI_API_KEY=...   # your Vertex-compatible key

    B) Project + Application Default Credentials (service account or gcloud):
      GOOGLE_GENAI_USE_VERTEXAI=true
      GOOGLE_CLOUD_PROJECT=your-project-id
      GOOGLE_CLOUD_LOCATION=us-central1   # optional, default us-central1
      # Do not set GEMINI_API_KEY if it would conflict; use ADC only.
    """
    load_dotenv(script_dir / ".env")

    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in (
        "1",
        "true",
        "yes",
    )
    project = (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip() or None
    location = (os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1").strip()
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip() or None

    if use_vertex:
        if project:
            print(f"[AUTH] Vertex AI — project={project}, location={location}")
            return genai.Client(vertexai=True, project=project, location=location)
        if api_key:
            print("[AUTH] Vertex AI — API key")
            return genai.Client(vertexai=True, api_key=api_key)
        sys.exit(
            "[ERROR] Vertex mode: set GOOGLE_GENAI_USE_VERTEXAI=true and either "
            "GOOGLE_CLOUD_PROJECT (+ ADC / gcloud auth), or GEMINI_API_KEY."
        )

    if not api_key:
        sys.exit(
            "[ERROR] Set GEMINI_API_KEY for Gemini Developer API, or "
            "GOOGLE_GENAI_USE_VERTEXAI=true for Vertex AI."
        )
    print("[AUTH] Gemini Developer API")
    return genai.Client(api_key=api_key)


def veo_model_name() -> str:
    return (os.getenv("VEO_MODEL") or "veo-3.1-fast-generate-preview").strip()


def gemini_model_name() -> str:
    return (os.getenv("GEMINI_MODEL") or "gemini-3-flash-preview").strip()


def vertex_publisher_model(short_model_id: str) -> str:
    """
    Vertex + API key: Client() cannot take project + api_key together, so the
    project/location must appear in the model resource name for Veo/Gemini.
    """
    s = short_model_id.strip()
    if s.startswith("projects/"):
        return s
    proj = (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
    if not proj:
        return s
    loc = (os.getenv("GOOGLE_CLOUD_LOCATION") or "us-central1").strip()
    return f"projects/{proj}/locations/{loc}/publishers/google/models/{s}"
