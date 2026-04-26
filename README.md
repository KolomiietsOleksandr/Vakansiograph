# LABO — Labor Market Intelligence API

A production-ready REST API service for analyzing federal job market data, skills demand, salary trends, and geographic distribution. Built with Flask, SQLite, and modern DevOps practices.

## 🚀 Features

- **Real-time Job Analytics** — Access 23K+ federal job postings
- **Skills Analysis** — ESCO normalization with skill classification (knowledge, competence, skill)
- **Salary Intelligence** — Trends by grade, department, location, and series code
- **Geographic Insights** — Job distribution by state with remote work analysis
- **RESTful API** — Clean, well-documented endpoints
- **Production-Ready** — Docker, CORS support, health checks, error handling

## 📋 Prerequisites

- Python 3.11+
- Docker & Docker Compose (optional)
- SQLite (included)

## 🔧 Quick Start

### Local Development

1. **Clone and setup:**
```bash
git clone <repo>
cd labo
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Run the development server:**
```bash
python main.py
```

Server runs on `http://localhost:5000`

### Docker Setup

```bash
docker-compose up --build
```

Access at `http://localhost` (via Nginx)

## 📁 Project Structure

```
labo/
├── app/
│   ├── __init__.py              # Flask app factory
│   ├── config.py                # Configuration (dev, prod, test)
│   ├── main.py                  # Development entry point
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py            # All API endpoints (blueprints)
│   │
│   ├── services/
│   │   ├── job_service.py       # Job queries
│   │   ├── skill_service.py     # Skill analytics
│   │   ├── salary_service.py    # Salary statistics
│   │   ├── location_service.py  # Geographic data
│   │   └── category_service.py  # Job categories
│   │
│   ├── models/
│   │   └── (Future: SQLAlchemy models)
│   │
│   ├── utils/
│   │   ├── database.py          # DB connection & queries
│   │   └── classifiers.py       # Skill classification, OPM series mapping
│   │
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css        # Main stylesheet
│   │   ├── js/
│   │   │   └── app.js           # Frontend JavaScript
│   │   └── images/
│   │
│   ├── templates/
│   │   └── index.html           # Main HTML (Flask template)
│   │
│   └── labor_market.db          # SQLite database
│
├── tests/
│   ├── test_api.py
│   ├── test_services.py
│   └── conftest.py
│
├── docker/
│   ├── Dockerfile
│   └── nginx.conf
│
├── docs/
│   ├── API.md
│   ├── SETUP.md
│   └── ARCHITECTURE.md
│
├── main.py                      # Development entry point
├── wsgi.py                      # Production WSGI entry point
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── QUICKSTART.md
```

## 🔌 API Endpoints

### Health & Overview
- `GET /api/health` — Service health check
- `GET /api/overview` — Market overview statistics

### Jobs
- `GET /api/jobs/recent?limit=20&keyword=python` — Recent job postings

### Skills
- `GET /api/skills/top?limit=20` — Top in-demand skills

### Salaries
- `GET /api/salaries?group_by=department` — Salary stats (group_by: department, series, state, grade)

### Locations
- `GET /api/locations` — Jobs by state with remote info

### Categories
- `GET /api/categories/summary` — Job categories overview
- `GET /api/categories/collection-status` — Data collection logs

## 📊 Example Request

```bash
curl http://localhost:5000/api/overview

# Response:
{
  "total_jobs": 23847,
  "total_organizations": 487,
  "avg_salary": {"min": 64200, "max": 118500},
  "remote_percentage": 31.4,
  "unique_skills": 612,
  "new_this_week": 3892
}
```

## 🧪 Testing

```bash
pytest
pytest --cov  # With coverage
```

## 🐳 Docker Commands

```bash
# Build and start
docker-compose up --build

# Run with hot-reload (development)
docker-compose up

# Stop services
docker-compose down

# View logs
docker-compose logs -f api
```

## 🔐 Environment Variables

See `.env.example`:
```
FLASK_ENV=development
DATABASE_PATH=app/labor_market.db
PORT=5000
CORS_ORIGINS=*
```

## 📖 Documentation

- **API Documentation** → `docs/API.md`
- **Setup Guide** → `docs/SETUP.md`
- **Architecture** → `docs/ARCHITECTURE.md`
- **Quick Start** → `QUICKSTART.md`

## 🛠️ Development

### Code Style
```bash
black app/  # Format code
flake8 app/ # Lint
```

### Adding New Endpoints

1. Create service in `app/services/`
2. Add route in `app/api/routes.py`
3. Write tests in `tests/`

Example:
```python
# app/services/my_service.py
class MyService:
    @staticmethod
    def get_data():
        return {"data": "value"}

# app/api/routes.py
@my_bp.route('/endpoint', methods=['GET'])
def my_endpoint():
    data = MyService.get_data()
    return jsonify(data), 200
```

## 📈 Performance

- SQLite queries optimized with proper indexing
- CORS enabled for cross-origin requests
- Health checks for monitoring
- Gunicorn with 4 workers for production

## 🚢 Deployment

### Production with Gunicorn
```bash
gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 60 wsgi:app
```

### Production with Docker
```bash
docker build -f docker/Dockerfile -t labo-api .
docker run -d -p 5000:5000 -e FLASK_ENV=production labo-api
```

## 📝 License

MIT

## 📧 Contact

For questions or issues, please contact the development team.
