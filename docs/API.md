# API Documentation — LABO Labor Market Intelligence

## Base URL
```
http://localhost:5000/api
```

## Authentication
Currently no authentication required (open API).

---

## Endpoints

### 1. Health Check

#### `GET /health`
Service health status.

**Response:**
```json
{
  "status": "healthy",
  "service": "LABO API"
}
```

---

### 2. Overview (Market Metrics)

#### `GET /overview`
Get high-level market statistics.

**Response:**
```json
{
  "total_jobs": 23847,
  "total_organizations": 487,
  "avg_salary": {
    "min": 64200,
    "max": 118500
  },
  "remote_percentage": 31.4,
  "unique_skills": 612,
  "new_this_week": 3892
}
```

**Fields:**
- `total_jobs` — Total job postings in database
- `total_organizations` — Number of unique federal agencies
- `avg_salary` — Average min/max salary across all jobs
- `remote_percentage` — % of positions offering telework
- `unique_skills` — Total unique skills tracked
- `new_this_week` — New postings in last 7 days

---

### 3. Recent Jobs

#### `GET /jobs/recent`
Get recent job postings with optional keyword search.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Number of results (max 100) |
| `keyword` | string | "" | Search in title and qualifications |

**Example:**
```
GET /jobs/recent?limit=10&keyword=python
```

**Response:**
```json
[
  {
    "position_id": "JZ-123456",
    "title": "Senior Python Developer",
    "organization": "Department of Labor",
    "department": "IT Services",
    "location_city": "Washington",
    "location_state": "DC",
    "min_salary": 95000,
    "max_salary": 135000,
    "salary_type": "annual",
    "job_grade": "GS-13",
    "series_code": "1550",
    "telework_eligible": true,
    "date_posted": "2026-03-27",
    "url": "https://usajobs.gov/..."
  }
]
```

---

### 4. Top Skills

#### `GET /skills/top`
Get most in-demand skills with classification.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 20 | Number of skills |

**Example:**
```
GET /skills/top?limit=15
```

**Response:**
```json
[
  {
    "skill": "Project Management",
    "type": "skill",
    "count": 4820
  },
  {
    "skill": "Communication",
    "type": "competence",
    "count": 4210
  },
  {
    "skill": "Python",
    "type": "knowledge",
    "count": 2340
  }
]
```

**Skill Types:**
- `knowledge` — Technical/professional knowledge (Python, SQL, AWS, etc.)
- `competence` — Soft skills (Communication, Leadership, Problem Solving)
- `skill` — General professional skills

---

### 5. Salary Statistics

#### `GET /salaries`
Get salary data grouped by specified dimension.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `group_by` | enum | department | Group by: `department`, `series`, `state`, `grade` |

**Examples:**

```
GET /salaries?group_by=grade
```

**Response (by Grade):**
```json
[
  {
    "label": "GS-13",
    "count": 1240,
    "avg_min": 78000,
    "avg_max": 142000
  }
]
```

```
GET /salaries?group_by=series
```

**Response (by Series — OPM Code):**
```json
[
  {
    "label": "Computer Science",
    "count": 3400,
    "avg_min": 82000,
    "avg_max": 152000
  }
]
```

**OPM Series Examples:**
- `1550` → Computer Science
- `1560` → Data Science
- `0801` → Engineering
- `0810` → Civil Engineering
- `0602` → Medical Officer

---

### 6. Geographic Distribution

#### `GET /locations`
Job distribution by state with salary and remote info.

**Response:**
```json
[
  {
    "location_state": "DC",
    "count": 5840,
    "avg_salary": 128000,
    "remote_count": 2570
  },
  {
    "location_state": "VA",
    "count": 4520,
    "avg_salary": 120000,
    "remote_count": 1808
  }
]
```

**Fields:**
- `location_state` — State abbreviation
- `count` — Total job postings
- `avg_salary` — Average maximum salary
- `remote_count` — Number of remote-eligible positions

---

### 7. Job Categories Summary

#### `GET /categories/summary`
Overview of job categories (OPM series codes).

**Response:**
```json
[
  {
    "category": "Medical",
    "series_code": "0602",
    "total_postings": 3200,
    "avg_salary": 95000,
    "remote_percentage": 12.5
  },
  {
    "category": "Engineering",
    "series_code": "0801",
    "total_postings": 2400,
    "avg_salary": 118000,
    "remote_percentage": 28.0
  }
]
```

---

### 8. Data Collection Status

#### `GET /categories/collection-status`
Latest data collection logs for monitoring.

**Response:**
```json
[
  {
    "series_code": "0301",
    "series_name": "Administration",
    "total_found": 450,
    "jobs_collected": 450,
    "started_at": "2026-03-27 10:30:00",
    "finished_at": "2026-03-27 10:35:00",
    "status": "success"
  }
]
```

---

## Error Handling

All errors return JSON with descriptive messages:

```json
{
  "error": "Invalid limit parameter"
}
```

**HTTP Status Codes:**
- `200` — Success
- `400` — Bad request
- `500` — Server error

---

## Rate Limiting

Not currently implemented. All endpoints are open.

---

## CORS

Cross-Origin Resource Sharing is enabled for all origins (`*`).

---

## Example Workflows

### Get market overview and top skills
```bash
curl http://localhost:5000/api/overview
curl http://localhost:5000/api/skills/top?limit=10
```

### Find Python jobs
```bash
curl "http://localhost:5000/api/jobs/recent?limit=5&keyword=python"
```

### Compare salaries by location
```bash
curl http://localhost:5000/api/salaries?group_by=state
curl http://localhost:5000/api/locations
```

### Monitor data collection
```bash
curl http://localhost:5000/api/categories/collection-status
```

---

## Future Enhancements

- [ ] Job recommendation engine
- [ ] Trend forecasting
- [ ] Advanced filtering
- [ ] Data export (CSV, Excel)
- [ ] Authentication & API keys
- [ ] Rate limiting
- [ ] GraphQL API

---

## Questions?

See README.md for project overview or SETUP.md for installation guide.
