# Browser Use + Veo 3.1 Snippets

This handoff gives the team a concrete integration seam for:

- reel discovery pipeline
- product discovery pipeline
- social media manager
- Veo 3.1 video generation from `avatar picture + prompt + product picture`
- full closed-loop storefront pipeline

Code lives in `integration/browser_use_veo31_snippets.py`.

## Verified locally

These repo paths were re-verified before adding the snippet:

- `uv run pytest packages/hackathon_pipelines/tests -q`
- `uv run pytest tests/runtime/test_owner_dashboard.py tests/runtime/test_control_plane.py -q`

That verification passed in this workspace on April 4, 2026.

## Important Veo note

The official Google Cloud docs say:

- Veo 3.1 GA model ID is `veo-3.1-generate-001`
- preview model `veo-3.1-generate-preview` was scheduled for discontinuation on April 2, 2026
- Veo 3.1 supports reference asset images, up to three subject images

So the snippet uses the GA model, not the preview one.

## Team handoff points

Your team still needs to finish these pieces:

1. Browser Use logged-in session handling
2. Cloud Storage upload helper for reference images
3. Any final Instagram upload hardening for live posting

Once those are ready, the main seam to replace is:

- `example_upload_reference_image()` in `integration/browser_use_veo31_snippets.py`

## Direct Veo call

Use:

```python
artifact = await run_direct_veo31_generation(
    project_id="your-gcp-project",
    output_gcs_uri="gs://your-bucket/generated-videos/",
    upload_reference_image=example_upload_reference_image,
    avatar_image_path="runtime_dashboard/static/uploads/avatars/avatar.png",
    product_image_path="runtime_dashboard/static/uploads/products/product.png",
    prompt="Create a short vertical Instagram storefront reel showing the creator holding the product, fast UGC pacing, strong opening hook, clean product closeups, ending CTA to shop now.",
)
```

## Full pipeline

Use:

```python
summary = await run_entire_storefront_pipeline(
    db_path="data/hackathon_pipelines.sqlite3",
    project_id="your-gcp-project",
    output_gcs_uri="gs://your-bucket/generated-videos/",
    upload_reference_image=example_upload_reference_image,
    avatar_image_path="runtime_dashboard/static/uploads/avatars/avatar.png",
    product_image_path="runtime_dashboard/static/uploads/products/product.png",
    media_path="output/hackathon_videos/generated_reel.mp4",
)
```
