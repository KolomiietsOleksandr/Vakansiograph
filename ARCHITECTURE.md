# VakansioGraph — Повна архітектура проекту

> Labor Market Intelligence Platform
> Версія: поточна (March 2026) | База: 120,493 вакансій | Країна: USA (USAJOBS)

---

## Зміст

1. [Загальна архітектура](#1-загальна-архітектура)
2. [Структура файлів](#2-структура-файлів)
3. [Шар збору даних — USAJOBS парсер](#3-шар-збору-даних--usajobs-парсер)
4. [Шар нормалізації — ESCO Pipeline](#4-шар-нормалізації--esco-pipeline)
5. [База даних — схема та логіка](#5-база-даних--схема-та-логіка)
6. [API сервер — Flask endpoints](#6-api-сервер--flask-endpoints)
7. [Сервіси — бізнес-логіка](#7-сервіси--бізнес-логіка)
8. [Frontend — побудова чартів](#8-frontend--побудова-чартів)
9. [Категоризація скілів](#9-категоризація-скілів)
10. [Lifecycle запиту — end-to-end](#10-lifecycle-запиту--end-to-end)
11. [Конфігурація та змінні середовища](#11-конфігурація-та-змінні-середовища)
12. [Масштабування на нові країни](#12-масштабування-на-нові-країни)

---

## 1. Загальна архітектура

```
┌────────────────────────────────────────────────────────────────────────────┐
│                        ЗОВНІШНІ ДЖЕРЕЛА ДАНИХ                              │
│  USAJOBS REST API  (https://data.usajobs.gov/api/search)                   │
│  → Федеральні вакансії США, ~270K+ активних оголошень                      │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │ HTTP (rate-limited, 0.5s між запитами)
                                ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  COLLECTOR  (usajobs_client_all.py)                                        │
│  USAJobsClient + DataCollector                                             │
│  • Пагінація до 250 результатів за запит                                   │
│  • Дедуплікація через collected_job_ids                                    │
│  • Парсинг JobPosting dataclass (28 полів)                                 │
│  • INSERT OR IGNORE → job_postings                                         │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  ESCO PIPELINE  (esco_normalizer.py)                                       │
│                                                                            │
│  ESCOLocalIndex (singleton)                                                │
│  ├─ завантажує skills_en.csv (13,960 скілів → 99,624 нормалізованих       │
│  │   термінів через preferredLabel + altLabels)                            │
│  ├─ будує ієрархічний граф через broaderRelationsSkillPillar_en.csv       │
│  └─ зберігається в пам'яті після першого завантаження                     │
│                                                                            │
│  SkillEnricher                                                             │
│  ├─ normalize_existing_skills() → UPDATE job_skills SET esco_*            │
│  └─ extract_and_enrich_all_jobs() → INSERT нові скіли з тексту вакансій   │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  SQLITE DATABASE  (app/labor_market.db)                                    │
│  job_postings (120,493) + job_skills (40,468) + допоміжні таблиці         │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  FLASK APP  (app/__init__.py → create_app())                               │
│  Blueprints: /api/jobs /api/skills /api/salaries                           │
│             /api/locations /api/categories /api/trends /api/overview      │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │ JSON responses
                                ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  BROWSER  (Chart.js + vanilla JS)                                          │
│  Сторінки: / (homepage) | /dashboard | /trends | /skills-intelligence     │
│  fetch() → /api/* → Chart.js рендеринг                                    │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Структура файлів

```
vakansiograph/
│
├── main.py                          # Точка входу — запускає Flask
├── requirements.txt
├── .env                             # USAJOBS_API_KEY, DB_PATH, тощо
│
├── ESCO dataset - v1.2.1/           # Локальний датасет European Skills Classification
│   ├── skills_en.csv                # 13,960 скілів з URI, preferredLabel, altLabels, skillType
│   ├── broaderRelationsSkillPillar_en.csv  # Граф батьківських зв'язків (для ієрархії)
│   └── skillGroups_en.csv           # Топ-рівневі групи таксономії
│
└── app/
    ├── __init__.py                  # Flask application factory (create_app)
    ├── config.py                    # Config/DevelopmentConfig/ProductionConfig
    ├── labor_market.db              # SQLite база даних
    │
    ├── api/
    │   └── routes.py                # Всі Flask blueprints та endpoint handlers
    │
    ├── services/                    # Бізнес-логіка
    │   ├── job_service.py           # Запити до job_postings
    │   ├── skill_service.py         # Топ скіли, ESCO статистика
    │   ├── salary_service.py        # Аналіз зарплат по grade/dept
    │   ├── location_service.py      # Географія вакансій
    │   ├── category_service.py      # OPM серії, collection status
    │   ├── trends_service.py        # Skill ROI, posting volume, skill-gap
    │   ├── esco_normalizer.py       # ESCO pipeline (ESCOLocalIndex + SkillEnricher)
    │   └── usajobs_client_all.py    # API клієнт + DataCollector (569 рядків)
    │
    ├── utils/
    │   ├── database.py              # get_db_connection() → sqlite3.Row factory
    │   └── classifiers.py          # OPM_SERIES_NAMES, classify_skill_type(),
    │                                # get_skill_category() (714 рядків)
    │
    ├── templates/
    │   ├── index.html               # Homepage зі stats
    │   ├── dashboard.html           # Основний дашборд (4 вкладки)
    │   ├── trends.html              # Ринкові тренди
    │   ├── skills_intelligence.html # Skills ROI + gap analysis
    │   ├── header.html              # Shared header (include)
    │   └── footer.html              # Shared footer (include)
    │
    └── static/
        ├── css/shared-styles.css    # CSS змінні, header, загальні стилі
        └── js/
            ├── app.js               # Логіка дашборду (712 рядків)
            └── chart.umd.min.js     # Chart.js (bundled, без CDN)
```

---

## 3. Шар збору даних — USAJOBS парсер

### Як працює `usajobs_client_all.py`

#### Крок 1 — HTTP запит до USAJOBS API

```python
class USAJobsClient:
    BASE_URL = "https://data.usajobs.gov/api/search"
    REQUEST_DELAY = 0.5  # секунди між запитами (rate limiting)

    def search(self, ResultsPerPage=250, Page=1, **kwargs) -> dict:
        # Headers: Host, User-Agent (email), Authorization (api_key)
        # Параметри: DatePosted, JobCategoryCode, LocationName, тощо
```

**Rate limiting**: після кожного запиту — `time.sleep(0.5)`. USAJOBS дозволяє ~100 req/хв.

#### Крок 2 — Пагінація

```python
def search_all(self, max_pages=20, **kwargs) -> Generator[JobPosting, None, None]:
    for page in range(1, max_pages + 1):
        data = self.search(Page=page, **kwargs)
        items = data["SearchResult"]["SearchResultItems"]
        if not items:
            break
        for item in items:
            yield self._parse_job(item)
```

Кожна сторінка — до 250 результатів. Зупиняється коли API повертає порожній список.

#### Крок 3 — Парсинг `_parse_job(item)`

Зі сирого JSON USAJOBS витягується `JobPosting` dataclass (28 полів):

| Поле | JSON шлях | Приклад |
|------|-----------|---------|
| `position_id` | `MatchedObjectId` | "552690500" |
| `title` | `MatchedObjectDescriptor.PositionTitle` | "Medical Officer" |
| `organization` | `PositionOrganization` | "Dept of Veterans Affairs" |
| `series_code` | `JobCategory[0].Code` | "0602" |
| `min_salary` | `PositionRemuneration[0].MinimumRange` | 85000.0 |
| `salary_type` | `PositionRemuneration[0].RateIntervalCode` | "Per Year" |
| `job_grade` | `JobGrade[0].Code` | "GS" → з `UserArea.Details.LowGrade` |
| `qualification_summary` | `UserArea.Details.MajorDuties` | текст 500-3000 символів |
| `telework_eligible` | `UserArea.Details.TeleworkEligible` | "Yes" |
| `hiring_path` | `UserArea.Details.HiringPath` | ["federal-employees"] |

**Визначення типу роботодавця** (`_determine_job_type`):
- Якщо organization містить "Army", "Navy", "Air Force" → "Military"
- Якщо "VA" або "Veterans" → "Veterans Affairs"
- Якщо "Federal" в who_may_apply → "Federal"

#### Крок 4 — Збереження (`DataCollector`)

```python
def collect_all(self, max_pages=20, date_posted=90):
    # 1. Перевірка дубліката через collected_job_ids (PRIMARY KEY → O(1))
    # 2. INSERT OR IGNORE → job_postings
    # 3. INSERT → collected_job_ids (for dedup)
    # 4. Checkpoint у ultimate_checkpoint (resume після краш)
```

**Деduplication**: таблиця `collected_job_ids` з `position_id TEXT PRIMARY KEY` — якщо вакансія вже є, `INSERT OR IGNORE` її мовчки пропускає. Завдяки цьому повторні запуски безпечні.

---

## 4. Шар нормалізації — ESCO Pipeline

### Що таке ESCO

European Skills, Competences, Qualifications and Occupations — стандартизована таксономія EU з 13,960 унікальних скілів, кожен з:
- `conceptUri` — унікальний URI (наприклад `http://data.europa.eu/esco/skill/75d8e5d9-...`)
- `preferredLabel` — офіційна назва ("lead others")
- `altLabels` — синоніми (\n-separated): "leadership", "leading people", "manage teams"...
- `skillType` — "knowledge" або "skill/competence"

### ESCOLocalIndex — побудова індексу

```python
class ESCOLocalIndex:
    _exact: dict[str, ESCOSkill]          # 99,624 нормалізованих термінів → ESCOSkill
    _short_terms: list[tuple[str, ESCOSkill]]  # 68,182 термінів ≤ 4 слова (для fuzzy)
    _hierarchy: dict[str, list[str]]      # URI → [parent1, parent2, ...] (для категорій)
```

**Завантаження** (запускається один раз, результат зберігається в пам'яті):

```
skills_en.csv (13,960 рядків)
    ↓ для кожного скіла беремо preferredLabel + всі altLabels
    ↓ нормалізуємо: lower() + strip() + collapse spaces
    ↓ записуємо в _exact dict
    ↓ якщо термін ≤ 4 слова → також у _short_terms (для fuzzy + extract)

broaderRelationsSkillPillar_en.csv
    ↓ будуємо dict: URI → (broaderURI, broaderLabel)
    ↓ для кожного skill URI walking up до 8 рівнів, поки не дійдемо до STOP_LABELS
    ↓ результат: _hierarchy[uri] = ["analytics and statistics", "S1", ...]
```

### Три стратегії нормалізації

```
raw_skill ("leadership")
    │
    ├─ 1. MANUAL_MAPPINGS         60+ US-специфічних термінів яких немає в ESCO
    │      "leadership" → ESCO URI + "lead others" + "skill/competence"
    │
    ├─ 2. Exact lookup             _exact.get(normalized_term)
    │      "project management" → точний збіг в індексі
    │
    └─ 3. Fuzzy lookup             SequenceMatcher через _short_terms
           threshold 0.82 — повертає найближчий збіг за similarity ratio
```

**Чому MANUAL_MAPPINGS**: ESCO використовує дієслівні фрази ("lead others"), а US ринок — іменники ("leadership"). Без маппінгів 40%+ найпоширеніших термінів не знаходяться.

### Витяг скілів з тексту вакансій (`extract_from_text`)

```python
def extract_from_text(self, text: str) -> list[ESCOSkill]:
    text_lower = normalize(text)
    for term, skill in self._short_terms:
        if len(term.split()) < 2:   # фільтр: мінімум 2 слова
            continue                 # уникаємо false positives (один символ "c", "r" тощо)
        if re.search(r"\b" + re.escape(term) + r"\b", text_lower):
            found[skill.uri] = skill  # URI як ключ → автоматична дедуплікація
    return list(found.values())
```

**Чому word-boundary (`\b`)**: без нього "programming" матчиться в "computer programming languages" як "program", "programming" і "computer programming" — три різні скіли для одного слова.

### SkillEnricher — запис в базу

**Step 1 — normalize_existing_skills()**:
```sql
-- Для кожного унікального skill_raw що вже є в job_skills
UPDATE job_skills
SET skill_esco_uri = ?, skill_esco_label = ?, skill_esco_type = ?, skill_category = ?
WHERE skill_raw = ?
```
Результат: 226/226 унікальних скілів отримали ESCO маппінг (100%).

**Step 2 — extract_and_enrich_all_jobs()**:
```sql
-- Знаходимо вакансії БЕЗ записів у job_skills
SELECT jp.position_id, qualification_summary || major_duties || title as text
FROM job_postings jp
LEFT JOIN job_skills js ON jp.position_id = js.position_id
WHERE js.position_id IS NULL

-- Для кожного знайденого скілу INSERT нового запису
INSERT OR IGNORE INTO job_skills
    (position_id, skill_raw, skill_esco_uri, skill_esco_label, skill_esco_type, skill_category)
VALUES (?, ?, ?, ?, ?, ?)
```

Підсумок: 40,468 записів у job_skills для 120,493 вакансій.

---

## 5. База даних — схема та логіка

### `job_postings` (120,493 рядків)

Головна таблиця. `position_id TEXT PRIMARY KEY` — унікальний ідентифікатор USAJOBS.

Ключові поля:
- `series_code` — OPM occupational series (376 унікальних, наприклад "0602" = Medical Officer)
- `salary_type` — "Per Year" (99,527), "Per Hour" (20,571), "Fee Basis" (44)
- `min_salary / max_salary` — для типу "Per Year": avg $67K–$98K
- `telework_eligible` — "Yes" / "No" / NULL
- `qualification_summary + major_duties` — джерело для витягу скілів (текст 500-5000 символів)

### `job_skills` (40,468 рядків)

```sql
CREATE TABLE job_skills (
    id              INTEGER PRIMARY KEY,
    position_id     TEXT,                    -- FK → job_postings
    skill_raw       TEXT,                    -- оригінальний термін з тексту
    skill_esco_uri  TEXT,                    -- http://data.europa.eu/esco/skill/...
    skill_esco_label TEXT,                   -- ESCO preferred label ("lead others")
    skill_esco_type  TEXT,                   -- "knowledge" | "skill/competence"
    skill_category   TEXT,                   -- "Management & Leadership", "IT & Technology"...
    FOREIGN KEY(position_id) REFERENCES job_postings(position_id)
);
```

226 унікальних скілів × 12 категорій:

| Категорія | Частка |
|-----------|--------|
| Management & Leadership | 30.2% |
| Healthcare & Medicine | 17.9% |
| Soft Skills & Communication | 12.9% |
| IT & Technology | 8.4% |
| Legal & Compliance | 8.0% |
| Security & Public Safety | 6.2% |
| Business & Finance | 6.2% |
| HR & Workforce | 5.8% |
| Sciences & Analytics | 3.6% |
| Engineering | 0.8% |
| Other | 0.02% |

### `ultimate_checkpoint` — resume механізм

Зберігає прогрес збору. Якщо скрипт падає на сторінці 150 з 500 — наступного разу продовжить з `cursor_position = 150`. Унікальний ключ: `(checkpoint_type, filter_key)`.

### `collected_job_ids` — дедуплікація

`position_id TEXT PRIMARY KEY` — існування запису означає "ця вакансія вже є в БД". `INSERT OR IGNORE` в job_postings + цю таблицю = нульова дублікація навіть при повторних запусках.

---

## 6. API сервер — Flask endpoints

### Application Factory (`app/__init__.py`)

```python
def create_app(config_name="development"):
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    # Реєстрація blueprints...
    # Маршрути для HTML сторінок...
    return app
```

### Всі endpoints

| Method | URL | Повертає |
|--------|-----|----------|
| GET | `/api/health` | `{"status": "healthy"}` |
| GET | `/api/overview` | total_jobs, orgs, avg_salary, skills, remote_% |
| GET | `/api/jobs/recent?limit=20&keyword=` | Список останніх вакансій |
| GET | `/api/skills/top?limit=20` | Топ скіли за частотою |
| GET | `/api/salaries?group_by=department` | Зарплати по groupBy полю |
| GET | `/api/locations` | Вакансії по штатах |
| GET | `/api/categories/summary` | OPM серії + coverage % |
| GET | `/api/categories/collection-status` | Статус збору даних |
| GET | `/api/trends/skill-roi?limit=20` | Скіли відсортовані за avg salary |
| GET | `/api/trends/category-salary` | Avg min/max salary по категоріях |
| GET | `/api/trends/skill-demand` | Топ-5 скілів на категорію |
| GET | `/api/trends/posting-volume` | Місячний об'єм вакансій |
| GET | `/api/trends/skills-by-category?category=X` | Drill-down скілів |

---

## 7. Сервіси — бізнес-логіка

### `job_service.py` — `get_overview()`

```python
# Фільтр зарплат — тільки "Per Year" і > $20K
SELECT AVG(min_salary), AVG(max_salary)
FROM job_postings
WHERE salary_type = 'Per Year' AND min_salary > 20000
```

Без цього фільтру: "Per Hour" ($19/год) та "Student Stipend" ($34K) тягнули середню вниз.

### `trends_service.py` — `get_skill_salary_roi()`

Ключовий запит для сторінки Skills Intelligence:

```sql
SELECT
    COALESCE(js.skill_esco_label, js.skill_raw) AS skill,
    js.skill_category,
    ROUND(AVG(jp.min_salary)) AS avg_min_salary,
    COUNT(DISTINCT jp.position_id) AS job_count
FROM job_skills js
JOIN job_postings jp ON js.position_id = jp.position_id
WHERE jp.salary_type = 'Per Year' AND jp.min_salary > 20000
GROUP BY skill
HAVING job_count > 30
ORDER BY avg_min_salary DESC
```

Результат: "provide patient care" → $137K avg min (топ-1, driven by VA doctors).

### `category_service.py` — захист від відсутності таблиці

```python
# Перевіряємо чи існує таблиця перш ніж питати
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='collection_log'")
if not c.fetchone():
    return []
```

---

## 8. Frontend — побудова чартів

### Технологічний стек

- **Chart.js** (bundled локально, `/static/js/chart.umd.min.js`) — без CDN залежності
- **Vanilla JS** — fetch() + DOM manipulation, без React/Vue
- **CSS Custom Properties** — темна тема через `--bg`, `--accent`, `--text-secondary`
- **Jinja2** — `{% include 'header.html' %}` для спільного хедера

### Патерн побудови чарту

Кожен чарт будується за однаковим патерном:

```javascript
// 1. Запит до API
fetch('/api/trends/skill-roi?limit=15')
  .then(r => r.json())
  .then(data => {
    // 2. Трансформація даних
    const labels = data.map(d => d.skill.slice(0, 26) + '…');
    const values = data.map(d => d.avg_min_salary);

    // 3. Ініціалізація Chart.js
    new Chart(document.getElementById('roiChart'), {
      type: 'bar',
      data: { labels, datasets: [{ data: values, backgroundColor: CHART_COLORS }] },
      options: {
        indexAxis: 'y',        // горизонтальні бари
        scales: {
          x: { ticks: { callback: v => '$' + Math.round(v/1000) + 'K' } }
        }
      }
    });
  });
```

### Типи чартів та де використовуються

| Тип | Де | Дані |
|-----|----|------|
| `line` | Trends — posting volume | `posting-volume` endpoint, 24 місяці |
| `bar` (horizontal) | Skills ROI, Top Skills | `skill-roi`, `skills/top` |
| `bar` (vertical) | Salary by grade | `salaries?group_by=job_grade` |
| `doughnut` | Category share, ESCO types | `skill-demand`, `skills/top` |
| `bubble` | Category × Salary | `category-salary` — x=jobs, y=salary, r=√jobs |
| `radar` | Skill demand radar | `skills/top` — 6 категорій |

### Глобальні налаштування (базовий об'єкт)

```javascript
const baseChartOpts = {
  responsive: true,
  plugins: {
    legend: { labels: { color: '#b0b0b0', font: { family: 'Outfit' } } },
    tooltip: { backgroundColor: '#1a1a1a', borderColor: '#2a2a2a', borderWidth: 1 }
  },
  scales: {
    x: { ticks: { color: '#b0b0b0' }, grid: { color: 'rgba(255,255,255,0.04)' } },
    y: { ticks: { color: '#b0b0b0' }, grid: { color: 'rgba(255,255,255,0.04)' } }
  }
};
```

Цей об'єкт spread-иться в кожен чарт для консистентного dark theme.

---

## 9. Категоризація скілів

### `classifiers.py` — три рівні категоризації

Функція `get_skill_category(label, esco_uri, esco_chain)` проходить три рівні:

```
Рівень 1: LABEL_TO_CATEGORY (150+ прямих маппінгів)
    "lead others" → "Management & Leadership"
    "amazon web services" → "IT & Technology"
    Точний збіг за label.lower() — O(1)
         │ якщо не знайдено ↓

Рівень 2: ESCO_GROUP_TO_CATEGORY (ієрархія)
    Проходимо ESCO chain: ["analytics and statistics", "transversal skills", ...]
    Кожен step перевіряємо проти ESCO_GROUP_TO_CATEGORY dict
    "analytics and statistics" → "Sciences & Analytics"
         │ якщо не знайдено ↓

Рівень 3: _CHAIN_KEYWORDS (keyword matching в chain string)
    chain_str = " ".join(esco_chain).lower()
    if any("health" in chain_str for ...) → "Healthcare & Medicine"
         │ якщо не знайдено ↓

Fallback: "Other"
```

### OPM Series Names

`classifiers.py` містить `OPM_SERIES_NAMES` — словник ~280 кодів:

```python
OPM_SERIES_NAMES = {
    "0110": "Economist",
    "0340": "Program Manager",
    "0602": "Medical Officer",
    "1102": "Contracting",
    "2210": "IT Management",
    # ... 280 кодів
}
```

Використовується для перетворення сирих кодів ("0602") в людські назви ("Medical Officer") на дашборді.

---

## 10. Lifecycle запиту — end-to-end

### Приклад: Dashboard завантажує "Top Skills"

```
Browser                     Flask                    SQLite
  │                            │                        │
  ├─ fetch('/api/skills/top') ─►                        │
  │                            ├─ SkillService          │
  │                            │  .get_top_skills()     │
  │                            │                        │
  │                            │  SELECT                │
  │                            │  COALESCE(skill_esco_label, skill_raw),
  │                            │  skill_esco_type,       │
  │                            │  COUNT(*) as count     │
  │                            │  FROM job_skills       │
  │                            │  GROUP BY display_label│
  │                            │  ORDER BY count DESC   │
  │                            │  LIMIT 20              │
  │                            │              ──────────►
  │                            │              ◄──────────
  │                            │  → [{"skill": "Recruit Employees",
  │                            │      "type": "skill/competence",
  │                            │      "count": 2054}, ...]
  │◄─ JSON response ──────────-┤                        │
  │                            │                        │
  ├─ Chart.js renderBarChart() │                        │
  │  labels = skills.map(s => s.skill)
  │  data = skills.map(s => s.count)
  │  new Chart(canvas, {type: 'bar', ...})
```

### Приклад: Нова вакансія додається в БД

```
USAJOBS API response (JSON)
    ↓
_parse_job() → JobPosting dataclass
    ↓
DataCollector.collect_all()
    ├─ CHECK collected_job_ids → якщо є, skip
    ├─ INSERT → job_postings (28 полів)
    └─ INSERT → collected_job_ids

    (пізніше, при enrichment запуску)
    ↓
SkillEnricher.extract_and_enrich_all_jobs()
    ├─ Знайти всі job_postings без job_skills записів
    ├─ Для кожної: extract_from_text(qualification_summary + major_duties)
    ├─ ESCOLocalIndex.normalize() → ESCOSkill
    ├─ get_category(uri, label) → "IT & Technology"
    └─ INSERT → job_skills (skill_raw, esco_uri, esco_label, esco_type, skill_category)
```

---

## 11. Конфігурація та змінні середовища

### `.env` файл

```env
USAJOBS_API_KEY=your_api_key_here
USAJOBS_EMAIL=your@email.com
DB_PATH=app/labor_market.db
DATABASE_PATH=app/labor_market.db    # підтримується обидва варіанти
FLASK_ENV=development
SECRET_KEY=your-secret-key
```

### `config.py` — читання env vars

```python
DATABASE_PATH = os.getenv("DATABASE_PATH",
                    os.getenv("DB_PATH",
                        os.path.join(BASE_DIR, "app", "labor_market.db")))
```

Fallback: `DATABASE_PATH` → `DB_PATH` → захардкоджений шлях відносно проекту.

---

## 12. Масштабування на нові країни

Платформа архітектурно готова до мульти-країнного розширення. Що потрібно зробити:

### Нове джерело даних

1. Створити `app/services/{country}_client.py` за аналогією `usajobs_client_all.py`
2. Реалізувати той самий інтерфейс: `JobPosting` dataclass → `INSERT → job_postings`
3. Додати поле `country TEXT` в `job_postings` (наразі захардкоджено "United States")

### Нова аналітика

- Додати фільтр `?country=US` до всіх `/api/*` endpoints
- Компаративні endpoint'и: `GET /api/compare/skill-demand?countries=US,DE,UK`
- "Emerging skills" = скіли з COUNT зростанням >20% за останні 90 днів (потребує timestamp на skill_raw появі)

### Потенційні джерела

| Країна | Джерело | API |
|--------|---------|-----|
| Germany | Bundesagentur für Arbeit | REST API |
| UK | Reed.co.uk / Indeed UK | Scraping або API |
| Canada | Job Bank Canada | Open Data API |


### ESCO вже готовий до мульти-країнного використання

ESCO — це EU стандарт, тому скіли вже нормалізовані в єдину таксономію незалежно від країни-джерела. Вакансія з Берліну і вакансія з Вашингтону з "project management" → однаковий ESCO URI → порівнянні дані.
