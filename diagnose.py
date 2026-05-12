"""
Діагностика бази даних та API
Запуск: python3.10 diagnose.py
"""
import sqlite3
import os
import json

DB_PATH = "labor_market.db"

if not os.path.exists(DB_PATH):
    print(f"❌ База даних не знайдена: {DB_PATH}")
    print("   Запустіть спочатку збір даних: python3.10 usajobs_client.py")
    exit(1)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

print("=" * 60)
print("  ДІАГНОСТИКА БАЗИ ДАНИХ")
print("=" * 60)

# 1. Таблиці
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f"\nТаблиці в БД: {tables}")

# 2. Кількість записів
for table in tables:
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    count = cur.fetchone()[0]
    print(f"  {table}: {count} записів")

# 3. Приклад вакансій
print("\n── Приклад вакансій (перші 3) ──")
cur.execute("SELECT position_id, title, organization, location_state, location_country, min_salary, max_salary, series_code, telework_eligible FROM job_postings LIMIT 3")
cols = [d[0] for d in cur.description]
for row in cur.fetchall():
    print("  ", dict(zip(cols, row)))

# 4. Навички
print("\n── Навички ──")
cur.execute("SELECT COUNT(*) FROM job_skills")
skill_count = cur.fetchone()[0]
print(f"  Всього записів у job_skills: {skill_count}")
if skill_count > 0:
    cur.execute("SELECT skill_raw, COUNT(*) as cnt FROM job_skills GROUP BY skill_raw ORDER BY cnt DESC LIMIT 10")
    print("  Топ-10:")
    for r in cur.fetchall():
        print(f"    {r[0]}: {r[1]}")
else:
    print("  ⚠ Таблиця job_skills ПОРОЖНЯ — навички не витягнулись")

# 5. Локації
print("\n── Локації ──")
cur.execute("SELECT location_state, COUNT(*) as cnt FROM job_postings WHERE location_state != '' GROUP BY location_state ORDER BY cnt DESC LIMIT 10")
locs = cur.fetchall()
if locs:
    print(f"  Топ-10 штатів:")
    for r in locs:
        print(f"    {r[0]}: {r[1]}")
else:
    print("  ⚠ Немає даних по штатах")
    cur.execute("SELECT location_state, location_country FROM job_postings LIMIT 5")
    print("  Приклад location_state/country:", cur.fetchall())

# 6. Зарплати
print("\n── Зарплати ──")
cur.execute("SELECT COUNT(*) FROM job_postings WHERE min_salary > 0")
sal_count = cur.fetchone()[0]
print(f"  Вакансій із зарплатою: {sal_count}")
cur.execute("SELECT AVG(min_salary), AVG(max_salary) FROM job_postings WHERE min_salary > 0")
row = cur.fetchone()
if row[0]:
    print(f"  Середня: ${row[0]:,.0f} – ${row[1]:,.0f}")

# 7. Серії
print("\n── OPM серії ──")
cur.execute("SELECT series_code, COUNT(*) as cnt FROM job_postings WHERE series_code != '' GROUP BY series_code ORDER BY cnt DESC LIMIT 10")
series = cur.fetchall()
if series:
    for r in series:
        print(f"    {r[0]}: {r[1]}")
else:
    print("  ⚠ series_code порожній")
    cur.execute("SELECT series_code, series_group FROM job_postings LIMIT 5")
    print("  Приклад:", cur.fetchall())

# 8. Departments
print("\n── Departments (для графіка зарплат) ──")
cur.execute("SELECT department, COUNT(*) FROM job_postings WHERE department != '' GROUP BY department ORDER BY 2 DESC LIMIT 10")
deps = cur.fetchall()
if deps:
    for r in deps:
        print(f"    {r[0]}: {r[1]}")
else:
    print("  ⚠ department порожній")

# 9. Categories summary check
print("\n── Перевірка categories/summary ──")
keywords = ["software engineer", "data scientist", "nurse", "civil engineer", "project manager"]
for kw in keywords:
    cur.execute("SELECT COUNT(*) FROM job_postings WHERE title LIKE ?", (f"%{kw}%",))
    c = cur.fetchone()[0]
    print(f"  '{kw}' в title: {c} збігів")

# 10. Collection log
print("\n── Лог збору ──")
cur.execute("SELECT series_code, series_name, jobs_collected, status FROM collection_log ORDER BY started_at DESC LIMIT 10")
for r in cur.fetchall():
    print(f"  {r[0]} ({r[1]}): {r[2]} jobs [{r[3]}]")

conn.close()

print("\n" + "=" * 60)
print("  РЕКОМЕНДАЦІЇ")
print("=" * 60)
if skill_count == 0:
    print("  → Навички не витягнулись. Це нормально якщо збір щойно запускався.")
    print("    Перезапустіть: python3.10 usajobs_client.py")
if not locs:
    print("  → Немає даних по штатах — перевірте що location_country = 'US'")
if sal_count == 0:
    print("  → Немає зарплат — перевірте парсинг salary")
print()
