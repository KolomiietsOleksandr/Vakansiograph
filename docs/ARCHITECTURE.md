# Architecture — LABO Design & Patterns

## Overview

LABO is built with a **layered architecture** pattern:

```
┌─────────────────────────────────────────┐
│         Frontend (HTML/CSS/JS)          │
│         - Templates (Jinja2)            │
│         - Static assets                 │
└────────────────┬────────────────────────┘
                 │ HTTP
┌────────────────▼────────────────────────┐
│        Flask Application Layer           │
│  - Routes & Blueprints (api/routes.py)  │
│  - CORS, Error handling                 │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│        Business Logic Layer              │
│  - Services (job, skill, salary, etc.)   │
│  - Data transformation                  │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│        Data Access Layer                 │
│  - Database utilities                   │
│  - SQLite queries                       │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│        Data Layer                        │
│  - SQLite Database                      │
│  - labor_market.db                      │
└─────────────────────────────────────────┘
```

---

## Directory Structure & Responsibilities

### `app/__init__.py`
**Flask Application Factory**
- Creates Flask app instance
- Registers blueprints
- Configures CORS
- Initializes logging

```python
def create_app(config_name: str = "development"):
    app = Flask(__name__)
    app.config.from_object(config_class)
    CORS(app)
    app.register_blueprint(jobs_bp)
    # ... other blueprints
    return app
```

### `app/config.py`
**Configuration Management**

Three environments:
1. **DevelopmentConfig** — Hot reload, debug=True
2. **ProductionConfig** — Optimized, debug=False
3. **TestingConfig** — In-memory DB

```python
class DevelopmentConfig(Config):
    DEBUG = True
    DATABASE_PATH = "app/labor_market.db"
```

### `app/api/routes.py`
**REST API Endpoints**

Uses Flask **Blueprints** for modular routing:
- `jobs_bp` — `/api/jobs/*`
- `skills_bp` — `/api/skills/*`
- `salaries_bp` — `/api/salaries/*`
- `locations_bp` — `/api/locations/*`
- `categories_bp` — `/api/categories/*`
- `health_bp` — `/api/health` & `/api/overview`

Example:
```python
@jobs_bp.route('/recent', methods=['GET'])
def recent_jobs():
    limit = request.args.get('limit', 20, type=int)
    keyword = request.args.get('keyword', '')
    data = JobService.get_recent_jobs(limit=limit, keyword=keyword)
    return jsonify(data), 200
```

**Benefits of Blueprints:**
- Logical separation of concerns
- Reusable route groups
- Easier testing & maintenance

### `app/services/`
**Business Logic Layer**

Each service handles a domain:

#### `job_service.py`
```python
class JobService:
    @staticmethod
    def get_overview():
        # Complex aggregations: total jobs, orgs, avg salary, etc.
    
    @staticmethod
    def get_recent_jobs(limit, keyword):
        # Search with filtering
```

#### `skill_service.py`
```python
class SkillService:
    @staticmethod
    def get_top_skills(limit):
        # Aggregates skills with classification
```

**Why separate services?**
- Logic isolated from routes
- Testable independently
- Reusable across endpoints
- Single Responsibility Principle

### `app/utils/`
**Helper Functions & Utilities**

#### `database.py`
Database connection management:
```python
def get_db_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row  # Return as dict-like objects
    return conn

def execute_query(query, params=()):
    # Execute SELECT, return results
```

#### `classifiers.py`
Data classification logic:
```python
def classify_skill_type(skill):
    # Returns: "knowledge", "competence", or "skill"

def get_series_name(code):
    # OPM code → human name (e.g., "1550" → "Computer Science")
```

**Why separate?**
- Reusable across services
- Easy to test
- Decoupled from DB logic

### `app/static/`
**Frontend Assets**

```
static/
├── css/
│   └── style.css        # Tailored dark theme
├── js/
│   └── app.js          # Dashboard logic, charts
└── images/             # Icons, logos
```

**Frontend Stack:**
- **HTML:** Jinja2 templates (Flask)
- **CSS:** Custom dark theme with gradients & animations
- **JS:** Vanilla (no framework) with Chart.js
- **Charts:** Chart.js for graphs & analytics

### `app/templates/`
**HTML Templates**

`index.html` — Single page application (SPA) with:
- Home page (features, CTA)
- Dashboard (4 tabs)
- Responsive design

Uses Jinja2 templating:
```html
<link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
<script src="{{ url_for('static', filename='js/app.js') }}"></script>
```

---

## Data Flow

### Example: `/api/overview` Request

```
1. HTTP GET /api/overview
   │
2. Flask routes to health_bp.overview()
   │
3. Calls JobService.get_overview()
   │
4. JobService uses database utilities:
   - get_db_connection()
   - execute_query()
   │
5. Database queries:
   - SELECT COUNT(*) FROM job_postings
   - SELECT AVG(min_salary, max_salary) ...
   - ... (4 more queries)
   │
6. Results processed and formatted:
   - avg_sal = round(values)
   - remote = round(percentage, 1)
   │
7. JSON response:
   {
     "total_jobs": 23847,
     "total_organizations": 487,
     ...
   }
   │
8. Browser receives & updates dashboard
```

---

## Database Schema (Simplified)

```sql
-- Main job postings
CREATE TABLE job_postings (
    position_id TEXT PRIMARY KEY,
    title TEXT,
    organization TEXT,
    department TEXT,
    location_city TEXT,
    location_state TEXT,
    min_salary REAL,
    max_salary REAL,
    salary_type TEXT,
    job_grade TEXT,
    series_code TEXT,
    telework_eligible BOOLEAN,
    date_posted DATE,
    qualification_summary TEXT,
    url TEXT
);

-- Skills required for jobs
CREATE TABLE job_skills (
    job_id TEXT,
    skill_raw TEXT,
    FOREIGN KEY (job_id) REFERENCES job_postings(position_id)
);

-- Data collection logs
CREATE TABLE collection_log (
    series_code TEXT,
    series_name TEXT,
    total_found INTEGER,
    jobs_collected INTEGER,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    status TEXT
);
```

---

## Request/Response Cycle

### Request Processing
```
Request → Flask Routing → Blueprint Handler → Service Layer
    ↓
Database Query → Process Data → Serialize → Response
```

### Response Format
All API responses are **JSON**:

**Success:**
```json
{
  "key": "value",
  "data": [...],
  "status": 200
}
```

**Error:**
```json
{
  "error": "descriptive message"
}
```

---

## Design Patterns Used

### 1. **Factory Pattern** (app creation)
```python
def create_app(config_name: str):
    app = Flask(__name__)
    # ... configuration
    return app
```

### 2. **Blueprints Pattern** (modular routes)
```python
jobs_bp = Blueprint('jobs', __name__, url_prefix='/api/jobs')

@jobs_bp.route('/recent', methods=['GET'])
def recent_jobs():
    ...
```

### 3. **Service Layer Pattern** (business logic)
```python
class JobService:
    @staticmethod
    def get_overview():
        # Logic separated from routes
```

### 4. **Static Methods** (utility functions)
```python
class LocationService:
    @staticmethod
    def get_locations():
        # No state needed
```

### 5. **Configuration Objects** (environment management)
```python
class Config:
    DATABASE_PATH = ...

class ProductionConfig(Config):
    DEBUG = False
```

---

## Scalability & Extension

### Adding a New Endpoint

1. **Create Service** (`app/services/new_service.py`)
```python
class NewService:
    @staticmethod
    def get_data():
        conn = get_db_connection()
        # ... query logic
        return results
```

2. **Create Route** (in `app/api/routes.py`)
```python
new_bp = Blueprint('new', __name__, url_prefix='/api/new')

@new_bp.route('/endpoint', methods=['GET'])
def new_endpoint():
    data = NewService.get_data()
    return jsonify(data), 200
```

3. **Register Blueprint** (in `app/__init__.py`)
```python
from app.api.routes import new_bp
app.register_blueprint(new_bp)
```

4. **Write Tests** (`tests/test_new.py`)
```python
def test_new_endpoint():
    response = client.get('/api/new/endpoint')
    assert response.status_code == 200
```

---

## Performance Considerations

### Current Optimizations
1. **SQLite Row Factory** — Dict-like access
2. **Index on frequently queried columns** — series_code, date_posted
3. **Limit results** — Prevent large data transfers
4. **Gunicorn workers** — Parallel request handling

### Future Optimizations
1. **Database** — Migrate to PostgreSQL for scale
2. **Caching** — Redis for frequently accessed data
3. **Pagination** — Offset/limit for large result sets
4. **Connection Pooling** — Reuse DB connections
5. **API Rate Limiting** — Protect against abuse

---

## Testing Architecture

```
tests/
├── conftest.py          # Pytest fixtures
├── test_api.py          # Endpoint tests
└── test_services.py     # Service layer tests
```

**Test Pattern:**
```python
def test_overview(client):
    response = client.get('/api/overview')
    assert response.status_code == 200
    data = response.get_json()
    assert 'total_jobs' in data
```

---

## Deployment Architecture

### Development
```
python main.py → Flask (debug=True, single process)
```

### Production
```
Nginx (reverse proxy)
  ↓
Gunicorn (4+ workers)
  ↓
Flask app instances
  ↓
SQLite database
```

Docker setup:
```yaml
services:
  api:
    build: .
    ports: 5000
    command: gunicorn wsgi:app
  
  nginx:
    image: nginx:alpine
    ports: 80
    depends_on: [api]
```

---

## Security Layers

1. **CORS** — Flask-CORS for cross-origin requests
2. **Input Validation** — Type hints, parameter checking
3. **Error Handling** — Generic error messages (no stack traces)
4. **Database** — SQLite (future: prepared statements)

---

## Environment Segregation

```
Development  → DevelopmentConfig  → debug=True, hot reload
Staging      → ProductionConfig   → debug=False, testing
Production   → ProductionConfig   → debug=False, gunicorn
```

Set via `.env`:
```
FLASK_ENV=development
```

---

## Key Takeaways

✅ **Modular** — Services, blueprints, configs
✅ **Testable** — Separated concerns
✅ **Scalable** — Easy to add endpoints/services
✅ **Maintainable** — Clear directory structure
✅ **Production-Ready** — Docker, error handling, health checks

---

## Related Documentation

- **README.md** — Project overview
- **SETUP.md** — Installation guide
- **API.md** — Endpoint documentation
