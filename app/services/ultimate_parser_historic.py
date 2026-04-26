#!/usr/bin/env python3
"""
🚀 ULTIMATE PARSER WITH HistoricJoa API (ПРАВИЛЬНА ВЕРСІЯ)
Використовує continuation token для пагінації - БЕЗ ЛІМІТІВ!

API Docs: https://developer.usajobs.gov/API-Reference/GET-api-HistoricJoa
"""

import os
import sys
import sqlite3
import requests
import json
from datetime import datetime

def init_db(db_path):
    """Создать таблицы"""
    print("✅ Инициализация БД...")
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # Таблиця вакансій
    cur.execute("""
        CREATE TABLE IF NOT EXISTS job_postings (
            position_id TEXT PRIMARY KEY,
            title TEXT,
            organization TEXT,
            department TEXT,
            location_city TEXT,
            location_state TEXT,
            location_country TEXT,
            min_salary REAL,
            max_salary REAL,
            salary_type TEXT,
            job_grade TEXT,
            series_code TEXT,
            series_group TEXT,
            qualification_summary TEXT,
            major_duties TEXT,
            education_requirements TEXT,
            travel_percentage TEXT,
            telework_eligible TEXT,
            date_posted TEXT,
            date_closing TEXT,
            url TEXT,
            who_may_apply TEXT,
            hiring_path TEXT,
            total_openings TEXT,
            job_type TEXT
        )
    """)
    
    # Таблиця навичок
    cur.execute("""
        CREATE TABLE IF NOT EXISTS job_skills (
            id INTEGER PRIMARY KEY,
            position_id TEXT,
            skill_raw TEXT,
            FOREIGN KEY(position_id) REFERENCES job_postings(position_id)
        )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Таблицы созданы\n")

def collect_jobs_historic(config, max_pages):
    """Собрать вакансії через HistoricJoa API с continuation token"""
    
    db_path = config['DB_PATH']
    email = config['USAJOBS_EMAIL']
    
    # Инициализировать БД
    init_db(db_path)
    
    # Загрузить существующие ID
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT position_id FROM job_postings")
    existing_ids = {row[0] for row in cur.fetchall()}
    conn.close()
    
    print(f"📍 Уже в БД: {len(existing_ids)} вакансій\n")
    
    # Параметры API
    base_url = "https://data.usajobs.gov/api/historicjoa"
    headers = {
        "User-Agent": email
    }
    
    collected = 0
    skipped = 0
    page = 1
    continuation_token = None  # Для первого запроса токен не нужен
    
    print("📡 Собираем через HistoricJoa API (БЕЗ ЛИМІТІВ)...\n")
    
    try:
        while page <= max_pages:
            # Токен уже URL-encoded з відповіді API — вставляємо напряму в URL,
            # щоб requests не кодував його вдруге (%3D → %253D)
            if continuation_token:
                url = f"{base_url}?continuationtoken={continuation_token}"
            else:
                url = base_url

            print(f"  📄 Страница {page}...", end=" ", flush=True)
            
            # Retry логика для 503 ошибок
            max_retries = 5
            retry_delay = 2  # Начальная задержка в секундах
            
            for attempt in range(max_retries):
                try:
                    # Запит до API
                    response = requests.get(url, headers=headers, timeout=30)
                    response.raise_for_status()
                    break  # Успех, выходим из цикла retry
                    
                except requests.exceptions.HTTPError as e:
                    if response.status_code == 503:
                        if attempt < max_retries - 1:
                            print(f"\n    ⚠️  Server перегружен (503), ждём {retry_delay}s...")
                            import time
                            time.sleep(retry_delay)
                            retry_delay *= 2  # Экспоненциальная задержка
                            continue
                    raise
            
            # Пауза между запросами (вежливость к серверу)
            import time
            time.sleep(1)
            
            data = response.json()
            
            # Перевірити чи є дані
            if 'data' not in data or not data['data']:
                print("✅ Конец данных")
                break
            
            jobs = data['data']
            print(f"({len(jobs)} вакансій)")
            
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            
            for job in jobs:
                # ID вакансії
                job_id = str(job.get('usajobsControlNumber', ''))
                if not job_id or job_id == '0':
                    continue
                
                # Пропустить дублікати
                if job_id in existing_ids:
                    skipped += 1
                    continue
                
                # Подготовить данные
                try:
                    title = job.get('positionTitle', '')
                    organization = job.get('hiringAgencyName', '')
                    department = job.get('hiringDepartmentName', '')
                    
                    # Позиція - це масив, беремо першу
                    locations = job.get('positionLocations', [])
                    location_city = locations[0].get('positionLocationCity', '') if locations else ''
                    location_state = locations[0].get('positionLocationState', '') if locations else ''
                    location_country = locations[0].get('positionLocationCountry', '') if locations else ''
                    
                    min_salary = float(job.get('minimumSalary', 0)) if job.get('minimumSalary') else 0
                    max_salary = float(job.get('maximumSalary', 0)) if job.get('maximumSalary') else 0
                    salary_type = job.get('salaryType', '')
                    job_grade = job.get('minimumGrade', '')
                    
                    # Категорії - це масив
                    job_categories = job.get('jobCategories', [])
                    series_code = job_categories[0].get('series', '') if job_categories else ''
                    
                    # Hiring paths - масив
                    hiring_paths = job.get('hiringPaths', [])
                    hiring_path = hiring_paths[0].get('hiringPath', '') if hiring_paths else ''
                    
                    date_posted = job.get('positionOpenDate', '')
                    date_closing = job.get('positionCloseDate', '')
                    telework = job.get('teleworkEligible', '')
                    who_may_apply = job.get('whoMayApply', '')
                    total_openings = job.get('totalOpenings', '')
                    work_schedule = job.get('workSchedule', '')
                    
                    # Вставить в БД
                    cur.execute("""
                        INSERT OR IGNORE INTO job_postings
                        (position_id, title, organization, department, location_city,
                         location_state, location_country, min_salary, max_salary, salary_type,
                         job_grade, series_code, date_posted, date_closing, telework_eligible,
                         who_may_apply, hiring_path, total_openings, job_type)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (job_id, title, organization, department, location_city,
                          location_state, location_country, min_salary, max_salary, salary_type,
                          job_grade, series_code, date_posted, date_closing, telework,
                          who_may_apply, hiring_path, total_openings, work_schedule))
                    
                    existing_ids.add(job_id)
                    collected += 1
                    
                except Exception as e:
                    print(f"    ⚠️ Ошибка: {e}")
                    continue
            
            conn.commit()
            conn.close()
            
            # Показать прогрес
            if collected % 500 == 0 and collected > 0:
                print(f"    ✅ Всього зібрано: {collected}")
            
            # Получить continuation token для следующей страницы
            paging = data.get('paging', {})
            metadata = paging.get('metadata', {})
            continuation_token = metadata.get('continuationToken')
            
            if not continuation_token:
                print(f"\n  ✅ Все данные загружены")
                break
            
            page += 1
        
        print(f"\n✅ Сбор завершен!")
        print(f"   • Новых вакансий: {collected}")
        print(f"   • Пропущено дублікатів: {skipped}")
        print(f"   • ВСЕГО В БД: {len(existing_ids)}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Ошибка API: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    import sys
    import os
    
    # Добавить корневую папку проекта в path
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    
    from app.services.usajobs_client_all import load_config
    
    config = load_config()
    
    if not config['USAJOBS_EMAIL']:
        print("❌ USAJOBS_EMAIL не установлен!")
        return False
    
    print("="*70)
    print("🚀 ULTIMATE PARSER - HistoricJoa API (БЕЗ ЛИМІТІВ!)")
    print("="*70)
    print()
    
    print("Выберите режим:")
    print("  1) FAST (50 страниц = ~50,000 вакансій, 5 хвилин)")
    print("  2) NORMAL (100 страниц = ~100,000 вакансій, 15 хвилин) ⭐")
    print("  3) MAXIMUM (250 страниц = ~250,000 вакансій, 30 хвилин)")
    print("  4) ULTRA (500 страниц = ~500,000 вакансій, 60 хвилин) 🚀")
    print()
    
    choice = input("Выберите (1-4): ").strip()
    
    if choice == '1':
        return collect_jobs_historic(config, 50)
    elif choice == '2':
        return collect_jobs_historic(config, 100)
    elif choice == '3':
        return collect_jobs_historic(config, 250)
    elif choice == '4':
        return collect_jobs_historic(config, 500)
    else:
        print("❌ Неверный выбор")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)