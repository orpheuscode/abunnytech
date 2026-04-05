# Video Pipeline

End-to-end video marketing pipeline: analyze videos with TwelveLabs Pegasus, synthesize patterns with Gemini, generate new videos with Veo 3.1.

## Setup

```bash
pip install -r requirements.txt
```

Add your API keys to `.env`:

```
TWELVELABS_API_KEY=your-key
GEMINI_API_KEY=your-key
```

## Pipeline Flow

### Step 1: Analyze videos with TwelveLabs Pegasus

```bash
python analyze.py shoemarketting1.mp4
```

Place videos in `input/videos/`. Outputs action, hook, and music analysis to `results.csv`.

### Step 2: Synthesize with Gemini and generate a new video prompt

```bash
python resultAnalyzegemini.py
```

Reads `results.csv` and `SocialMediaPipeline.csv`, sends to Gemini, outputs to `Total Analysis Output.txt` and automatically copies to `input/veo/user_prompt.txt`.

### Step 3: Generate video with Veo 3.1

```bash
python generate.py
```

Reads `input/veo/` (system_prompt.txt, user_prompt.txt, product.jpg, avatar.jpg) and generates a video to `output/`.

## Folder Structure

```
video-pipeline/
  input/
    videos/          <- put marketing videos here for analysis
    veo/             <- Veo inputs: product.jpg, avatar.jpg, system_prompt.txt, user_prompt.txt
  output/            <- generated videos land here
  analyze.py         <- Step 1: TwelveLabs Pegasus analysis
  resultAnalyzegemini.py  <- Step 2: Gemini synthesis
  generate.py        <- Step 3: Veo 3.1 generation
  results.csv        <- analysis output database
  SocialMediaPipeline.csv <- additional video data
  Total Analysis Output.txt <- Gemini output
  requirements.txt
  .env               <- API keys (not committed)
```
