"""
Labor Market Monitor — REST API Server
========================================
Flask API для дашборду. Запити адаптовані під реальну структуру даних USAJOBS.
"""

import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
import json

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

DB_PATH = os.environ.get("DATABASE_PATH", os.environ.get("DB_PATH", "labor_market.db"))

OPM_SERIES_NAMES = {
    "0301": "Administration", "0341": "Admin Officer", "0343": "Program Analyst",
    "0346": "Logistics", "0201": "Human Resources", "0501": "Finance",
    "0510": "Accounting", "0560": "Budget Analyst", "0602": "Medical Officer",
    "0610": "Nurse", "0620": "Practical Nurse", "0631": "Occ. Therapist",
    "0660": "Pharmacist", "0680": "Dental Officer", "0801": "Engineering",
    "0810": "Civil Engineering", "0830": "Mechanical Eng.", "0850": "Electrical Eng.",
    "0854": "Computer Eng.", "0855": "Electronics Eng.", "0905": "Attorney",
    "0950": "Paralegal", "0110": "Economist", "0401": "Biological Science",
    "1301": "Physical Science", "2210": "IT Management", "1550": "Computer Science",
    "1560": "Data Science", "1801": "Investigation", "1811": "Criminal Investigator",
    "2152": "Air Traffic Control", "1102": "Contracting", "1101": "Business",
    "0025": "Park Ranger", "0028": "Environmental", "0080": "Security",
    "0089": "Emergency Mgmt", "0018": "Safety/Health",
}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def classify_skill_type(skill):
    knowledge = {
        "python","java","javascript","typescript","sql","c++","c#","aws","azure","gcp",
        "docker","kubernetes","linux","react","angular","node.js","postgresql","mongodb",
        "cybersecurity","network security","information security","machine learning",
        "deep learning","nlp","artificial intelligence","cloud computing","data science",
        "statistics","chemistry","biology","civil engineering","mechanical engineering",
        "electrical engineering","nursing","pharmacy","clinical","healthcare","public health",
        "accounting","excel","powerpoint","tableau","power bi","sap","sharepoint",
        "microsoft office","computer vision","autocad","solidworks","terraform","git",
    }
    competence = {
        "communication","leadership","problem solving","critical thinking","teamwork",
        "writing","public speaking","negotiation","analytical thinking","decision making",
    }
    s = skill.lower()
    if s in knowledge: return "knowledge"
    if s in competence: return "competence"
    return "skill"


@app.route("/api/overview")
def overview():
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM job_postings")
    total = c.fetchone()[0]

    c.execute("SELECT COUNT(DISTINCT organization) FROM job_postings")
    orgs = c.fetchone()[0]

    c.execute("SELECT AVG(min_salary), AVG(max_salary) FROM job_postings WHERE min_salary > 0")
    r = c.fetchone()
    avg_sal = {"min": round(r[0] or 0), "max": round(r[1] or 0)}

    c.execute("SELECT SUM(CASE WHEN telework_eligible THEN 1 ELSE 0 END)*100.0/MAX(COUNT(*),1) FROM job_postings")
    remote = round(c.fetchone()[0] or 0, 1)

    c.execute("SELECT COUNT(DISTINCT skill_raw) FROM job_skills")
    skills = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM job_postings WHERE date_posted >= date('now','-7 days')")
    week = c.fetchone()[0]
    if week == 0: week = total

    conn.close()
    return jsonify({"total_jobs":total,"total_organizations":orgs,"avg_salary":avg_sal,"remote_percentage":remote,"unique_skills":skills,"new_this_week":week})


@app.route("/api/skills/top")
def top_skills():
    limit = request.args.get("limit", 20, type=int)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT skill_raw, COUNT(*) as count FROM job_skills GROUP BY skill_raw ORDER BY count DESC LIMIT ?", (limit,))
    results = [{"skill": r["skill_raw"].title(), "type": classify_skill_type(r["skill_raw"]), "count": r["count"]} for r in c.fetchall()]
    conn.close()
    return jsonify(results)


@app.route("/api/salaries")
def salaries():
    group_by = request.args.get("group_by", "department")
    conn = get_db()
    c = conn.cursor()

    if group_by == "series":
        c.execute("""SELECT series_code as label, COUNT(*) as count, AVG(min_salary) as avg_min, AVG(max_salary) as avg_max
            FROM job_postings WHERE min_salary > 0 AND series_code != '' GROUP BY series_code HAVING count > 3 ORDER BY avg_max DESC LIMIT 15""")
        results = []
        for r in c.fetchall():
            d = dict(r); d["label"] = OPM_SERIES_NAMES.get(d["label"], d["label"]); results.append(d)
    elif group_by == "state":
        c.execute("""SELECT location_state as label, COUNT(*) as count, AVG(min_salary) as avg_min, AVG(max_salary) as avg_max
            FROM job_postings WHERE min_salary > 0 AND location_state != '' GROUP BY location_state HAVING count > 3 ORDER BY avg_max DESC LIMIT 20""")
        results = [dict(r) for r in c.fetchall()]
    elif group_by == "grade":
        c.execute("""SELECT job_grade as label, COUNT(*) as count, AVG(min_salary) as avg_min, AVG(max_salary) as avg_max
            FROM job_postings WHERE min_salary > 0 AND job_grade != '' GROUP BY job_grade ORDER BY avg_max DESC""")
        results = [dict(r) for r in c.fetchall()]
    else:
        c.execute("""SELECT department as label, COUNT(*) as count, AVG(min_salary) as avg_min, AVG(max_salary) as avg_max
            FROM job_postings WHERE min_salary > 0 AND department != '' GROUP BY department HAVING count > 3 ORDER BY avg_max DESC LIMIT 15""")
        results = [dict(r) for r in c.fetchall()]

    conn.close()
    return jsonify(results)


@app.route("/api/locations")
def locations():
    conn = get_db()
    c = conn.cursor()
    # No country filter — actual data has "United States" not "US"
    c.execute("""SELECT location_state, COUNT(*) as count, AVG(max_salary) as avg_salary,
        SUM(CASE WHEN telework_eligible THEN 1 ELSE 0 END) as remote_count
        FROM job_postings WHERE location_state != '' GROUP BY location_state ORDER BY count DESC LIMIT 20""")
    results = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(results)


@app.route("/api/jobs/recent")
def recent_jobs():
    limit = request.args.get("limit", 20, type=int)
    keyword = request.args.get("keyword", "")
    conn = get_db()
    c = conn.cursor()
    if keyword:
        c.execute("""SELECT position_id, title, organization, department, location_city, location_state,
            min_salary, max_salary, salary_type, job_grade, series_code, telework_eligible, date_posted, url
            FROM job_postings WHERE title LIKE ? OR qualification_summary LIKE ? ORDER BY date_posted DESC LIMIT ?""",
            (f"%{keyword}%", f"%{keyword}%", limit))
    else:
        c.execute("""SELECT position_id, title, organization, department, location_city, location_state,
            min_salary, max_salary, salary_type, job_grade, series_code, telework_eligible, date_posted, url
            FROM job_postings ORDER BY date_posted DESC LIMIT ?""", (limit,))
    results = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(results)


@app.route("/api/categories/summary")
def categories_summary():
    conn = get_db()
    c = conn.cursor()
    # Group by actual series_code, not keyword search
    c.execute("""SELECT series_code, COUNT(*) as total, AVG(max_salary) as avg_salary,
        SUM(CASE WHEN telework_eligible THEN 1 ELSE 0 END)*100.0/MAX(COUNT(*),1) as remote_pct
        FROM job_postings WHERE series_code != '' GROUP BY series_code HAVING total > 0 ORDER BY total DESC LIMIT 20""")
    results = [{"category": OPM_SERIES_NAMES.get(r["series_code"], r["series_code"]),
                "series_code": r["series_code"], "total_postings": r["total"],
                "avg_salary": round(r["avg_salary"] or 0), "remote_percentage": round(r["remote_pct"] or 0, 1)}
               for r in c.fetchall()]
    conn.close()
    return jsonify(results)


@app.route("/api/collection/status")
def collection_status():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT series_code, series_name, total_found, jobs_collected, started_at, finished_at, status FROM collection_log ORDER BY started_at DESC LIMIT 20")
    results = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify(results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)