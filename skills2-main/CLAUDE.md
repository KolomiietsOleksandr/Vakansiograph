# CLAUDE.md — skills2

## Project Overview

ESCO Skill Mapping Pipeline: extracts skills from Ukrainian job vacancies **and CVs/resumes**, then normalizes them to ESCO taxonomy URIs.

**Stage 1 — Extraction**: pull skills from vacancy/resume text (platform-provided raw skills or LLM-extracted from description)

**Stage 2 — Normalization**: map extracted skills to ESCO using fuzzy matching, semantic embeddings, and LLM re-ranking enriched with ESCO graph traversal (parent/sibling expansion)

- Vacancy dataset: `KSE-RESEARCH-Group/Work_UA_vacancies` (HuggingFace)
- Resume dataset: `KSE-RESEARCH-Group/Work_UA_resumes` (HuggingFace, 104k resumes)
- ESCO version: v1.2.1, Ukrainian (`uk`) and English (`en`) CSV files

---

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in GEMINI_API_KEY
```

---

## Common Commands

```bash
# Run pipeline (fuzzy mapper, 10 samples)
.venv/bin/python scripts/run_pipeline.py --mapper fuzzy --sample 10 --output output/test.jsonl

# Run all mappers
.venv/bin/python scripts/run_pipeline.py --mapper all --sample 20 --output output/all.jsonl

# Use mock ESCO index (no API needed)
.venv/bin/python scripts/run_pipeline.py --mapper fuzzy --sample 5 --esco-index tests/fixtures/mock_esco.json

# Run with local vLLM server (gpt-oss 120b), batch 64, resume on crash
.venv/bin/python scripts/run_pipeline.py \
  --mapper llm_two_stage \
  --provider vllm \
  --vllm-base-url http://localhost:8000/v1 \
  --vllm-model gpt-oss-120b \
  --batch-size 64 \
  --resume \
  --output output/results.jsonl

# Run vllm_optimized mapper (best for small local models like Qwen3-30B-A3B)
# Sends 1 skill + ~10 candidates per request for maximum vLLM throughput
.venv/bin/python scripts/run_pipeline.py \
  --mapper vllm_optimized \
  --provider vllm \
  --vllm-base-url http://localhost:8000/v1 \
  --vllm-model Qwen/Qwen3-30B-A3B-Instruct-2507-FP8 \
  --batch-size 64 \
  --resume \
  --output output/results.jsonl

# --- Resume / CV pipeline ---

# Run pipeline on resumes (fuzzy mapper, 10 samples)
.venv/bin/python scripts/run_pipeline.py --source resumes --mapper fuzzy --sample 10 --output output/cv_results.jsonl

# CV-weighted mapper: multi-signal candidate retrieval from work experience + education
.venv/bin/python scripts/run_pipeline.py --source resumes --mapper cv_weighted --sample 10 --output output/cv_results.jsonl

# Smoke test resumes with mock ESCO (no API needed)
.venv/bin/python scripts/run_pipeline.py --source resumes --mapper fuzzy --sample 5 --esco-index tests/fixtures/mock_esco.json

# Pre-compute ESCO embeddings (one-time, requires Gemini key)
.venv/bin/python scripts/precompute_embeddings.py

# Verify embeddings work
.venv/bin/python scripts/verify_embeddings.py

# Evaluate against gold standard
.venv/bin/python scripts/evaluate.py gold_standard.json output/results.jsonl

# Run tests (no API key needed)
.venv/bin/pytest tests/
```

Mapper choices: `fuzzy`, `embedding`, `llm_direct`, `llm_two_stage`, `vllm_optimized`, `cv_weighted`, `all`

Data source: `--source vacancies` (default) or `--source resumes`

---

## Architecture

| Module | Purpose |
|--------|---------|
| `esco_pipeline/config.py` | `Settings` (pydantic-settings, reads `.env`) |
| `esco_pipeline/models.py` | `Vacancy`, `Resume`, `Document`, `ESCOMapping`, `DocumentResult`, `SkillSource` |
| `esco_pipeline/esco_interface.py` | `ESCOIndexInterface` ABC; `MockESCOIndex` (tests); `ESCOIndex` (production) |
| `esco_pipeline/llm_client.py` | Unified LLM client: Gemini or vLLM (OpenAI-compatible) backends |
| `esco_pipeline/extractors/` | Stage 1: `PlatformExtractor` (raw skills), `LLMExtractor` |
| `esco_pipeline/mappers/` | Stage 2: `FuzzyMapper`, `EmbeddingMapper`, `LLMMapper` (direct + two-stage), `CVWeightedMapper` |
| `esco_pipeline/enrichment.py` | Graph traversal: expands candidates via ESCO parent/sibling relations, returns per-URI scores and categories |
| `esco_pipeline/pipeline.py` | Deduplicates skills, runs mapper once per unique skill, builds per-doc results |
| `esco_pipeline/evaluation.py` | Precision/recall/F1/unmapped/hallucination metrics |
| `scripts/run_pipeline.py` | Main CLI entry point |

---

## Key Technical Details

- **ESCO data path**: `esco/ESCO dataset - v1.2.1 - classification - {lang} - csv/`
- **Embedding cache**: `esco/.embeddings_cache_{lang}.npz` (normalized float32 vectors)
- **LLM caching**: `DiskCache` in `.cache/` — SHA256-keyed JSON files
- **Rate limiting**: Gemini API capped at 3000 RPM in `ESCOIndex`
- **Tests use**: `MockESCOIndex` from `tests/fixtures/mock_esco.json` (no API needed)
- **LLM mapper** validates URIs via `uri_exists()` before returning to catch hallucinations
- **Scored candidate ranking** (`LLMMapper._select_candidates`): candidates are scored by source (fuzzy confidence, embedding cosine sim, graph parent discount × 0.7, graph sibling similarity). Selection guarantees minimum slots per category (fuzzy 15, embedding 15, sibling 5, parent 3), fills remaining by global score, and sorts descending so the LLM sees the best candidates first. Near-exact fuzzy matches (>=0.95) get a +0.15 boost.
- **CV mapper** (`cv_weighted`) uses multi-signal candidate retrieval: work experience (position + responsibilities overlap boost), education (faculty), merged with section-based weights
- **CV extraction** uses structured `CV_EXTRACTION_PROMPT` with labeled sections (work experience, education, additional info)

---

## Environment Variables

```
GEMINI_API_KEY=      # Required for embedding and LLM mappers (Gemini provider)
LLM_PROVIDER=gemini  # "gemini" (default) or "vllm"
```

vLLM / OpenAI-compatible server (only when `LLM_PROVIDER=vllm`):

```
VLLM_BASE_URL=http://localhost:8000/v1
VLLM_MODEL=gpt-oss-120b
VLLM_API_KEY=EMPTY
```

Optional overrides (all have defaults in `Settings`):

```
GEMINI_MODEL=gemini-2.5-flash
ESCO_LANGUAGE=uk
SAMPLE_SIZE=
FUZZY_THRESHOLD=80.0
EMBEDDING_THRESHOLD=0.72
CV_EXPERIENCE_WEIGHT=0.8
CV_EDUCATION_WEIGHT=0.5
CV_OVERLAP_BOOST=1.3
```

---

## Testing

```bash
.venv/bin/pytest tests/
```

All tests use `MockESCOIndex` — no API key needed.

Quick smoke test:
```bash
.venv/bin/python scripts/run_pipeline.py --mapper fuzzy --sample 5 --esco-index tests/fixtures/mock_esco.json
```
