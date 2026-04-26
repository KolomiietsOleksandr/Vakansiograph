# 🚀 VakansioGraph - Setup Guide

## 📋 Project Structure

```
vakansiograph/
├── app/
│   ├── templates/
│   │   ├── index.html          (🏠 Homepage)
│   │   └── dashboard.html      (📊 Dashboard)
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css       (🎨 Styling)
│   │   └── js/
│   │       └── app.js          (⚙️ Dashboard Logic)
│   ├── api/routes.py           (API endpoints)
│   ├── services/               (Business logic)
│   ├── utils/database.py       (Database helpers)
│   ├── config.py               (Configuration)
│   ├── __init__.py             (Flask factory)
│   └── labor_market.db         (SQLite 71MB)
├── main.py                     (Entry point - port 5001)
└── requirements.txt            (Python deps)
```

---

## 🎯 What's New

### Homepage (`index.html`)
- ✅ Beautiful landing page with VakansioGraph branding
- ✅ Hero section with stats (23.8K jobs, 612 skills, etc.)
- ✅ 6 feature cards (Analytics, Intelligence, Geography, Skills, Salary, Trends)
- ✅ 4 interactive dashboard cards (Overview, Skills, Salaries, Geography)
- ✅ Professional footer with links
- ✅ Smooth animations and hover effects

### Dashboard (`dashboard.html`)
- ✅ Header with logo and navigation
- ✅ 4 tabs: Overview | Skills & ESCO | Salaries | Geography
- ✅ All interactive charts using Chart.js
- ✅ Real-time data from Flask API
- ✅ Responsive grid layout

### Styling (`style.css`)
- ✅ Dark theme (#0a0a0a background)
- ✅ Neon accent colors:
  - Primary: `#00ff41` (bright green)
  - Secondary: `#ff006e` (hot pink)
  - Tertiary: `#00d4ff` (cyan)
- ✅ Smooth animations and transitions
- ✅ Mobile responsive

### JavaScript (`app.js`)
- ✅ Dashboard tab switching
- ✅ All chart rendering functions:
  - Trend chart (30 days)
  - Recent jobs list
  - Category/OPM series chart
  - ESCO stats
  - Skills list with filters
  - Skill type distribution chart
  - Demand radar
  - Salary by department
  - Salary by state
  - Federal pay grades
  - Geographic distribution
  - Remote work percentages

---

## 🏃 Quick Start

### 1️⃣ Start Flask Server

```bash
cd vakansiograph
python main.py
```

Output:
```
 * Running on http://127.0.0.1:5001
```

### 2️⃣ Open in Browser

```
http://localhost:5001
```

This opens the **Homepage** first!

### 3️⃣ Navigate to Dashboard

Click **"Explore Dashboard"** button or use the navigation links.

---

## 📖 Page Flows

### Homepage → Dashboard
```
index.html (landing page)
    ↓
[Explore Dashboard] → dashboard.html
    ↓
Select tab (Overview, Skills, Salaries, Geography)
    ↓
View interactive charts & data
    ↓
Click [← Home] to return to homepage
```

### Direct URLs
- Homepage: `http://localhost:5001/`
- Dashboard: `http://localhost:5001/dashboard`
- Dashboard with tab: `http://localhost:5001/dashboard#skills`

---

## 🎨 Design Features

### Colors
| Name | Hex | Usage |
|------|-----|-------|
| Accent | `#00ff41` | Buttons, metrics, highlights |
| Secondary | `#ff006e` | Alternative highlights |
| Tertiary | `#00d4ff` | Charts, accents |
| Background | `#0a0a0a` | Main background |
| Surface | `#141414` | Cards background |
| Border | `#2a2a2a` | Borders, dividers |

### Typography
- **Font Family**: Outfit (sans-serif)
- **Mono Font**: IBM Plex Mono
- **Sizes**: 
  - Hero h1: 3.5rem
  - Section h2: 2.2rem
  - Card title: 1rem
  - Body: 0.9-1.1rem

---

## 📊 Dashboard Tabs

### 📊 Overview Tab
- **5 Metrics**: Total postings, new this week, avg salary, remote %, skills
- **Posting Trends**: 30-day line chart with 5 categories
- **Latest Postings**: Recent job listings
- **OPM Series**: Horizontal bar chart of job categories

### 🎓 Skills & ESCO Tab
- **ESCO Normalization**: 87.3% matching rate + breakdown by type
- **Skill Type Distribution**: Donut chart (Knowledge/Skill/Competence)
- **Demand Radar**: 8-axis radar chart current vs 6 months ago
- **Top Skills**: Sortable list with filters

### 💰 Salaries Tab
- **Salary by Department**: Min/Max horizontal bars
- **Salary by State**: Vertical bars for 12 top states
- **Federal Pay Grades**: GS-5 through SES cards with ranges

### 🗺️ Geography Tab
- **Job Distribution**: All states bar chart
- **Remote Work %**: State-by-state percentages
- **State Analysis**: Comprehensive table with postings, salary, remote%

---

## 🔗 API Endpoints Used

```
GET  /api/overview           → Market overview stats
GET  /api/skills/top         → Top 20 skills
GET  /api/locations          → State-by-state data
GET  /api/salaries           → Salary by department
GET  /api/jobs/recent        → Recent job postings
GET  /api/categories/summary → Job categories
```

---

## 🎯 Customization

### Change Brand Name
**File**: `templates/index.html` + `templates/dashboard.html`
```html
<!-- Change from "VakansioGraph" to your name -->
<a href="#" class="logo">
  <div class="logo-icon">⚡</div>
  YOUR_BRAND_NAME
</a>
```

### Change Colors
**File**: `static/css/style.css`
```css
:root {
  --accent: #00ff41;              /* Primary neon green */
  --accent-secondary: #ff006e;    /* Pink */
  --accent-tertiary: #00d4ff;     /* Cyan */
}
```

### Add More Stats to Homepage
**File**: `templates/index.html`
```html
<div class="stat">
  <div class="stat-num">YOUR_NUMBER</div>
  <div class="stat-label">YOUR_LABEL</div>
</div>
```

---

## 📱 Responsive Design

Tested on:
- ✅ Desktop (1920px+)
- ✅ Laptop (1200px)
- ✅ Tablet (768px)
- ✅ Mobile (375px)

The layout automatically stacks columns on smaller screens.

---

## 🐛 Troubleshooting

### Dashboard shows no data
1. Make sure Flask API is running: `python main.py`
2. Check console for errors (F12 → Console tab)
3. Try refreshing (CTRL+F5)

### Charts not rendering
1. Ensure Chart.js CDN is loaded (check Network tab)
2. Canvas elements must exist in HTML (they do!)
3. Clear browser cache and reload

### Styles look wrong
1. Clear cache: CTRL+SHIFT+DELETE
2. Hard refresh: CTRL+SHIFT+R
3. Check if style.css is loaded in Network tab

---

## 📞 Support Files

- `index-home.html` - Homepage (rename to `index.html` in production)
- `dashboard-updated.html` - Dashboard (rename to `dashboard.html`)
- `app.js` - JavaScript logic for charts
- `style.css` - Global styling
- `vakansiograph.zip` - Complete project

---

## ✨ Features Implemented

- [x] Beautiful homepage with hero section
- [x] Interactive dashboard with 4 tabs
- [x] Real-time data from Flask API
- [x] Chart.js integration (8+ chart types)
- [x] Responsive mobile design
- [x] Smooth animations
- [x] Dark theme with neon accents
- [x] Navigation between homepage and dashboard
- [x] ESCO skill classification display
- [x] Federal pay grade analysis
- [x] Geographic insights
- [x] Remote work statistics

---

## 🚀 Deployment Notes

For production:
1. Rename `index-home.html` → `index.html`
2. Rename `dashboard-updated.html` → `dashboard.html`
3. Update Flask routes to serve both templates
4. Consider adding caching headers
5. Minify CSS/JS for performance
6. Add HTTPS redirect

---

**Made with ❤️ for VakansioGraph**
