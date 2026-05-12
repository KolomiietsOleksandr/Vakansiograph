from flask import Blueprint, jsonify, request
from app.services.job_service import JobService
from app.services.skill_service import SkillService
from app.services.salary_service import SalaryService
from app.services.location_service import LocationService
from app.services.category_service import CategoryService
from app.services.trends_service import TrendsService
from app import cache

jobs_bp = Blueprint('jobs', __name__, url_prefix='/api/jobs')
skills_bp = Blueprint('skills', __name__, url_prefix='/api/skills')
salaries_bp = Blueprint('salaries', __name__, url_prefix='/api/salaries')
locations_bp = Blueprint('locations', __name__, url_prefix='/api/locations')
categories_bp = Blueprint('categories', __name__, url_prefix='/api/categories')
trends_bp = Blueprint('trends', __name__, url_prefix='/api/trends')
health_bp = Blueprint('health', __name__, url_prefix='/api')


@health_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "service": "LABO API"}), 200


@health_bp.route('/overview', methods=['GET'])
@cache.cached(timeout=600)
def overview():
    try:
        data = JobService.get_overview()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@jobs_bp.route('/recent', methods=['GET'])
def recent_jobs():
    try:
        limit = request.args.get('limit', 20, type=int)
        keyword = request.args.get('keyword', '')
        data = JobService.get_recent_jobs(limit=limit, keyword=keyword)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@skills_bp.route('/top', methods=['GET'])
@cache.cached(timeout=600, query_string=True)
def top_skills():
    try:
        limit = request.args.get('limit', 20, type=int)
        country = request.args.get('country', 'ALL').upper()
        data = SkillService.get_top_skills(limit=limit, country=country)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@salaries_bp.route('', methods=['GET'])
@cache.cached(timeout=600, query_string=True)
def salaries():
    try:
        group_by = request.args.get('group_by', 'department')
        data = SalaryService.get_salaries(group_by=group_by)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@locations_bp.route('', methods=['GET'])
@cache.cached(timeout=600)
def locations():
    try:
        data = LocationService.get_locations()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@categories_bp.route('/summary', methods=['GET'])
@cache.cached(timeout=600)
def categories_summary():
    try:
        data = CategoryService.get_categories_summary()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@categories_bp.route('/collection-status', methods=['GET'])
def collection_status():
    try:
        data = CategoryService.get_collection_status()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/skill-roi', methods=['GET'])
@cache.cached(timeout=600, query_string=True)
def skill_roi():
    try:
        limit = request.args.get('limit', 20, type=int)
        data = TrendsService.get_skill_salary_roi(limit=limit)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/category-salary', methods=['GET'])
@cache.cached(timeout=600)
def category_salary():
    try:
        data = TrendsService.get_category_salary()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/skill-demand', methods=['GET'])
@cache.cached(timeout=600)
def skill_demand():
    try:
        data = TrendsService.get_skill_demand_by_category()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/posting-volume', methods=['GET'])
@cache.cached(timeout=600, query_string=True)
def posting_volume():
    try:
        data = TrendsService.get_posting_volume_by_month()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/skills-by-category', methods=['GET'])
@cache.cached(timeout=600, query_string=True)
def skills_by_category():
    try:
        category = request.args.get('category', '')
        limit = request.args.get('limit', 10, type=int)
        if not category:
            return jsonify({"error": "category param required"}), 400
        data = TrendsService.get_top_skills_by_category(category, limit=limit)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/countries', methods=['GET'])
@cache.cached(timeout=600)
def countries():
    try:
        data = TrendsService.get_available_countries()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/country-stats', methods=['GET'])
@cache.cached(timeout=600, query_string=True)
def country_stats():
    try:
        country = request.args.get('country', 'ALL').upper()
        data = TrendsService.get_country_stats(country)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/posting-volume-by-country', methods=['GET'])
@cache.cached(timeout=600, query_string=True)
def posting_volume_by_country():
    try:
        country = request.args.get('country', 'ALL').upper()
        data = TrendsService.get_posting_volume_by_country(country)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/skill-country-breakdown', methods=['GET'])
def skill_country_breakdown():
    try:
        skill = request.args.get('skill', '')
        if not skill:
            return jsonify({"error": "skill param required"}), 400
        data = TrendsService.get_skill_country_breakdown(skill)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/skill-detail', methods=['GET'])
def skill_detail():
    try:
        skill = request.args.get('skill', '')
        if not skill:
            return jsonify({"error": "skill param required"}), 400
        data = TrendsService.get_skill_detail(skill)
        if not data:
            return jsonify({"error": "skill not found"}), 404
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/skill-timeline', methods=['GET'])
def skill_timeline():
    try:
        skill = request.args.get('skill', '')
        country = request.args.get('country', 'ALL')
        if not skill:
            return jsonify({"error": "skill param required"}), 400
        data = TrendsService.get_skill_timeline(skill=skill, country=country)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
