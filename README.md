# Vakansiograph

Labor market intelligence dashboard that aggregates job postings from USAJOBS, Adzuna, and Jooble, maps extracted skills to the ESCO taxonomy via LLM, and surfaces salary, skills, and geographic trends through a REST API + web UI.

## Stack

- **Backend:** Flask 3, SQLite (WAL), APScheduler, Gunicorn
- **Caching:** Redis (production) / FileSystemCache (dev fallback) + `analytics_cache` DB table
- **Skill Enrichment:** Google Gemini 2.5 Flash — skill extraction, ESCO fuzzy/embedding/LLM mapping
- **Frontend:** Jinja2 templates, Chart.js 4.5
- **Infrastructure:** Docker Compose, Nginx

## Prerequisites

- Python 3.11+
- Docker & Docker Compose (for containerized runs)
- API keys (see below)

## Environment Variables

Copy `.env.example` and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Description |
|---|---|
| `USAJOBS_API_KEY` | USAJOBS API key |
| `USAJOBS_EMAIL` | Email registered with USAJOBS |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna API credentials |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | Model ID (default: `gemini-2.5-flash`) |
| `DATABASE_PATH` | SQLite path (default: `./app/labor_market.db`) |
| `FLASK_ENV` | `development` or `production` |
| `REDIS_URL` | Redis URL (production only, e.g. `redis://redis:6379/0`) |

## Deployment

### Local development

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

App runs at `http://localhost:5001`. The scheduler thread starts automatically and begins collecting jobs in the background.

### Docker (development)

```bash
docker-compose up --build
```

Uses `docker-compose.override.yml` for live reload. Access at `http://localhost` (Nginx on port 80).

### Docker (production)

```bash
docker-compose -f docker-compose.prod.yml up --build -d
```

Adds a Redis service, disables debug mode, and runs Gunicorn with multiple workers.

### Bare-metal production (Gunicorn)

```bash
pip install -r requirements.txt
gunicorn --bind 0.0.0.0:5001 --workers 4 --threads 2 --timeout 60 wsgi:app
```

Run the scheduler as a separate process alongside Gunicorn (it's started by `main.py`; for production, wrap it in a systemd unit or supervisor).

## Project Structure

```
app/
  api/routes.py           # 25+ API endpoints
  services/               # Business logic + APScheduler jobs
    scheduler.py          # collect → extract skills → ESCO enrich → build analytics
    analytics_builder.py  # cache layer for expensive aggregations
    esco_enricher_v2.py   # ESCO hybrid mapper orchestrator
  utils/database.py       # SQLite connection, indexes, pragmas
  templates/              # Jinja2 HTML (index, countries, trends, skills_intelligence)
  static/js/app.js        # Chart.js data fetching + rendering
esco_pipeline/            # Standalone ESCO enrichment pipeline
  mappers/                # fuzzy_mapper, embedding_mapper, llm_mapper
scripts/
  create_golden_dataset.py
  eval_llm.py             # Precision/recall evaluation against golden dataset
docker/
  Dockerfile
  nginx.conf
docker-compose.yml
docker-compose.prod.yml
wsgi.py                   # Gunicorn entry point
main.py                   # Dev entry point (with scheduler thread)
```

## Key API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/overview` | Market overview (totals, avg salary, remote %) |
| GET | `/api/jobs/recent` | Recent postings (`?limit=20&keyword=python`) |
| GET | `/api/skills/top` | Top skills (`?limit=20&country=US`) |
| GET | `/api/salaries` | Salary stats (`?group_by=department\|series\|state\|grade`) |
| GET | `/api/locations` | Jobs by state/country |
| GET | `/api/trends/skill-roi` | Skills ranked by avg salary |
| GET | `/api/trends/posting-volume` | Monthly posting trends |
| GET | `/api/trends/country-stats` | Country-level breakdown (`?country=US`) |
| GET | `/api/insights/hero-stats` | 6 AI-generated market stat cards |
| POST | `/api/admin/rebuild-cache` | Force rebuild analytics cache |

## Testing

```bash
pytest
pytest --cov   # with coverage report
```

LLM evaluation against the golden dataset:

```bash
python scripts/eval_llm.py
# or via API: POST /api/admin/eval-llm
```

## Code Quality

```bash
black app/
flake8 app/
```
