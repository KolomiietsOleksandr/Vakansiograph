# Setup Guide — LABO Installation & Configuration

## Prerequisites

- **Python:** 3.11 or higher
- **pip:** Python package manager
- **Git:** Version control
- **Docker** (optional): For containerized deployment
- **SQLite3:** Usually comes with Python

Check versions:
```bash
python --version
pip --version
git --version
sqlite3 --version
```

---

## Local Development Setup

### 1. Clone Repository
```bash
git clone https://github.com/yourusername/labo.git
cd labo
```

### 2. Create Virtual Environment

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**On Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Verify activation:**
```bash
which python  # Should show venv path
```

### 3. Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**What gets installed:**
- `Flask==3.0.0` — Web framework
- `Flask-CORS==4.0.0` — Cross-origin support
- `python-dotenv==1.0.0` — Environment variables
- `gunicorn==21.2.0` — Production WSGI server
- Plus testing & dev tools

### 4. Configure Environment

Copy the example file:
```bash
cp .env.example .env
```

Edit `.env` with your settings:
```ini
FLASK_ENV=development
DATABASE_PATH=app/labor_market.db
PORT=5000
CORS_ORIGINS=*
```

### 5. Verify Database

Check that `app/labor_market.db` exists:
```bash
ls -lh app/labor_market.db
sqlite3 app/labor_market.db ".tables"
```

Expected tables:
- `job_postings`
- `job_skills`
- `collection_log`

### 6. Run Development Server

```bash
python main.py
```

Output:
```
 * Running on http://0.0.0.0:5000
 * Debug mode: on
```

### 7. Test the API

In another terminal:
```bash
curl http://localhost:5000/api/health
curl http://localhost:5000/api/overview
```

---

## Docker Setup

### 1. Prerequisites
- Docker Desktop installed
- Running on macOS, Windows, or Linux

### 2. Build and Run

```bash
docker-compose up --build
```

This:
- Builds the Flask API container
- Starts Nginx reverse proxy
- Exposes on `http://localhost`

### 3. View Logs
```bash
docker-compose logs -f api
docker-compose logs -f nginx
```

### 4. Stop Services
```bash
docker-compose down
```

### 5. Clean Up
```bash
docker-compose down -v  # Remove volumes too
docker system prune     # Clean unused images
```

---

## Project Structure Reference

```
labo/
├── app/                          # Main application package
│   ├── __init__.py              # Flask factory
│   ├── config.py                # Dev/prod/test configs
│   ├── labor_market.db          # SQLite database
│   │
│   ├── api/
│   │   └── routes.py            # All endpoints
│   │
│   ├── services/
│   │   ├── job_service.py
│   │   ├── skill_service.py
│   │   ├── salary_service.py
│   │   ├── location_service.py
│   │   └── category_service.py
│   │
│   ├── utils/
│   │   ├── database.py          # DB connection helpers
│   │   └── classifiers.py       # Data classification logic
│   │
│   ├── static/
│   │   ├── css/style.css        # Styles
│   │   ├── js/app.js            # Frontend logic
│   │   └── images/              # Images
│   │
│   └── templates/
│       └── index.html           # Main HTML
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
│   ├── API.md                   # Endpoint documentation
│   ├── SETUP.md                 # This file
│   └── ARCHITECTURE.md
│
├── main.py                      # Development entry point
├── wsgi.py                      # Production WSGI entry
├── requirements.txt
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

---

## Common Tasks

### Run Tests
```bash
# All tests
pytest

# With coverage
pytest --cov=app

# Specific test file
pytest tests/test_api.py -v
```

### Format Code
```bash
black app/
flake8 app/
```

### Add New Dependencies
```bash
pip install new-package
pip freeze > requirements.txt
```

### Update Database Path
Edit `.env`:
```ini
DATABASE_PATH=/path/to/new/labor_market.db
```

### Switch to Production Mode
Edit `.env`:
```ini
FLASK_ENV=production
```

### Run with Gunicorn (like production)
```bash
gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 60 wsgi:app
```

---

## Troubleshooting

### Port already in use
```bash
# Find process using port 5000
lsof -i :5000

# Kill it
kill -9 <PID>

# Or use different port
export PORT=5001
python main.py
```

### Database not found
```bash
# Verify path
ls -l app/labor_market.db

# Check config
cat .env | grep DATABASE_PATH
```

### Module import errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --force-reinstall

# Check Python path
python -c "import sys; print(sys.path)"
```

### CORS errors
```bash
# Check CORS setting in .env
cat .env | grep CORS_ORIGINS

# Update if needed
CORS_ORIGINS=http://localhost:3000
```

### Docker issues
```bash
# Rebuild from scratch
docker-compose down -v
docker-compose up --build --no-cache

# Check logs
docker-compose logs api
```

---

## Performance Tuning

### Production Settings

`.env`:
```ini
FLASK_ENV=production
DEBUG=False
```

### Gunicorn Workers
```bash
# For 4-core CPU: 2-4 workers
gunicorn --workers 4 --worker-class sync wsgi:app

# For 8-core CPU: 4-8 workers
gunicorn --workers 8 --worker-class sync wsgi:app
```

### Database Optimization
```sql
-- Create indexes for faster queries
CREATE INDEX idx_job_series ON job_postings(series_code);
CREATE INDEX idx_job_posted ON job_postings(date_posted);
CREATE INDEX idx_skill_raw ON job_skills(skill_raw);
```

---

## Monitoring

### Health Check
```bash
curl http://localhost:5000/api/health
```

### Docker Health Status
```bash
docker-compose ps
```

### Logs
```bash
# Flask logs
docker-compose logs api -f

# All logs
docker-compose logs -f
```

---

## Security Recommendations

### Before Deployment:

1. **Environment variables:**
   - Never commit `.env` files
   - Use `.env.example` as template
   - Store secrets in secure vaults

2. **Database:**
   - Restrict file permissions: `chmod 600 labor_market.db`
   - Use backups

3. **API:**
   - Implement authentication (JWT tokens)
   - Add rate limiting
   - Validate all inputs
   - Use HTTPS in production

4. **Dependencies:**
   - Regular updates: `pip install --upgrade -r requirements.txt`
   - Check for vulnerabilities: `pip-audit`

---

## Next Steps

1. Read **API.md** for endpoint details
2. Check **ARCHITECTURE.md** for design patterns
3. Start the server and explore the dashboard
4. Read the code to understand the structure

---

## Support

For issues or questions:
- Check this guide first
- Search GitHub issues
- Contact the development team

Happy coding! 🚀
