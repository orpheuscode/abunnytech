# Video Pipeline

End-to-end video marketing pipeline: analyze videos with TwelveLabs Pegasus, synthesize patterns with Gemini, generate new videos with **Veo 3.1 Fast** (Gemini API).

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in keys.

**Gemini Developer API (default):** set `GEMINI_API_KEY` only (do not set `GOOGLE_GENAI_USE_VERTEXAI`).

**Vertex AI:** set `GOOGLE_GENAI_USE_VERTEXAI=true` and either:

- `GEMINI_API_KEY` **and** `GOOGLE_CLOUD_PROJECT` (and usually `GOOGLE_CLOUD_LOCATION`, default `us-central1`). The project ID is required so Veo uses a full Vertex resource path.  
- Or `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` with Application Default Credentials only (`gcloud auth application-default login` or a service account; leave `GEMINI_API_KEY` unset).

Optional: `VEO_MODEL` and `GEMINI_MODEL` if your project uses different resource names than the defaults (`veo-3.1-fast-generate-preview`, `gemini-3-flash-preview`). To use standard (non-fast) Veo 3.1 instead, set `VEO_MODEL=veo-3.1-generate-preview`.

## Pipeline Flow

### Step 1: Analyze videos with TwelveLabs Pegasus

```bash
python analyze.py your_clip.mp4
```

Place videos in `input/videos/`. Outputs action, hook, and music analysis to `results.csv` (one row appended per run).

### Step 2: Synthesize with Gemini and refresh the Veo user prompt

```bash
python resultAnalyzegemini.py
```

Reads `results.csv` and `SocialMediaPipeline.csv`, sends to Gemini, writes `Total Analysis Output.txt` and **`input/veo/user_prompt.txt`** (used by `generate.py`).

### Step 3: Generate video with Veo 3.1 Fast

```bash
python generate.py              # one 8s clip → output/veo_<timestamp>.mp4
python generate.py --extend     # 8s seed + extension API; saves only the extended clip as veo_<timestamp>.mp4
```

Default output is **vertical 9:16**. Each run produces **a single MP4** under `output/` (no duplicate filenames, no local ffmpeg step).

On Windows you can double-click **`generate_16.bat`** for the `--extend` flow.

Optional: `input/veo/extend_prompt.txt` — custom prompt for the extension step (second API call). The first 8s clip is not saved to disk; it is only used to seed the extension, and the remote seed file is deleted on the Gemini Developer API when possible.

Reads `input/veo/` (`system_prompt.txt`, `user_prompt.txt`, `avatar_1.*`, `avatar_2.*`, optional `product.*`) and writes to `output/`.

## Folder Structure

```
video-pipeline/
  input/
    videos/          <- put marketing videos here for analysis
    veo/             <- Veo 3.1 Fast: avatar_1.*, avatar_2.*, optional product.*, system_prompt.txt, user_prompt.txt
  output/            <- generated videos (veo_<timestamp>.mp4)
  analyze.py         <- Step 1: TwelveLabs Pegasus analysis
  resultAnalyzegemini.py  <- Step 2: Gemini synthesis
  generate.py        <- Step 3: Veo 3.1 Fast generation
  generate_16.bat    <- Windows: run generate.py --extend
  results.csv        <- analysis output database
  SocialMediaPipeline.csv <- additional video data
  Total Analysis Output.txt <- Gemini output
  requirements.txt
  .env               <- API keys (not committed)
```
