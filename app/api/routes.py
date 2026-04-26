"""
API Routes - Flask Blueprints for all endpoints
"""

from flask import Blueprint, jsonify, request
from app.services.job_service import JobService
from app.services.skill_service import SkillService
from app.services.salary_service import SalaryService
from app.services.location_service import LocationService
from app.services.category_service import CategoryService
from app.services.trends_service import TrendsService

# Define blueprints
jobs_bp = Blueprint('jobs', __name__, url_prefix='/api/jobs')
skills_bp = Blueprint('skills', __name__, url_prefix='/api/skills')
salaries_bp = Blueprint('salaries', __name__, url_prefix='/api/salaries')
locations_bp = Blueprint('locations', __name__, url_prefix='/api/locations')
categories_bp = Blueprint('categories', __name__, url_prefix='/api/categories')
trends_bp = Blueprint('trends', __name__, url_prefix='/api/trends')
health_bp = Blueprint('health', __name__, url_prefix='/api')


# ==================== HEALTH ====================
@health_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "service": "LABO API"}), 200


@health_bp.route('/overview', methods=['GET'])
def overview():
    """Get overview statistics"""
    try:
        data = JobService.get_overview()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== JOBS ====================
@jobs_bp.route('/recent', methods=['GET'])
def recent_jobs():
    """Get recent job postings"""
    try:
        limit = request.args.get('limit', 20, type=int)
        keyword = request.args.get('keyword', '')
        data = JobService.get_recent_jobs(limit=limit, keyword=keyword)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== SKILLS ====================
@skills_bp.route('/top', methods=['GET'])
def top_skills():
    """Get top skills by frequency, optionally filtered by country"""
    try:
        limit = request.args.get('limit', 20, type=int)
        country = request.args.get('country', 'ALL').upper()
        data = SkillService.get_top_skills(limit=limit, country=country)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== SALARIES ====================
@salaries_bp.route('', methods=['GET'])
def salaries():
    """Get salary statistics grouped by specified field"""
    try:
        group_by = request.args.get('group_by', 'department')
        data = SalaryService.get_salaries(group_by=group_by)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== LOCATIONS ====================
@locations_bp.route('', methods=['GET'])
def locations():
    """Get job statistics by location"""
    try:
        data = LocationService.get_locations()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== CATEGORIES ====================
@categories_bp.route('/summary', methods=['GET'])
def categories_summary():
    """Get job categories summary"""
    try:
        data = CategoryService.get_categories_summary()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@categories_bp.route('/collection-status', methods=['GET'])
def collection_status():
    """Get data collection status"""
    try:
        data = CategoryService.get_collection_status()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==================== TRENDS ====================
@trends_bp.route('/skill-roi', methods=['GET'])
def skill_roi():
    """Skills ranked by average salary of jobs requiring them"""
    try:
        limit = request.args.get('limit', 20, type=int)
        data = TrendsService.get_skill_salary_roi(limit=limit)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/category-salary', methods=['GET'])
def category_salary():
    """Average salary range per skill category"""
    try:
        data = TrendsService.get_category_salary()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/skill-demand', methods=['GET'])
def skill_demand():
    """Top skills grouped by category (for skill-gap analysis)"""
    try:
        data = TrendsService.get_skill_demand_by_category()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/posting-volume', methods=['GET'])
def posting_volume():
    """Monthly job posting counts"""
    try:
        data = TrendsService.get_posting_volume_by_month()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/skills-by-category', methods=['GET'])
def skills_by_category():
    """Top skills for a specific category"""
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
def countries():
    """Available countries with job counts"""
    try:
        data = TrendsService.get_available_countries()
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/country-stats', methods=['GET'])
def country_stats():
    """KPIs for a specific country"""
    try:
        country = request.args.get('country', 'ALL').upper()
        data = TrendsService.get_country_stats(country)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/posting-volume-by-country', methods=['GET'])
def posting_volume_by_country():
    """Monthly job posting counts filtered by country"""
    try:
        country = request.args.get('country', 'ALL').upper()
        data = TrendsService.get_posting_volume_by_country(country)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@trends_bp.route('/skill-country-breakdown', methods=['GET'])
def skill_country_breakdown():
    """Country distribution for a skill"""
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
    """Full details for a skill"""
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
    """Monthly demand for a specific skill, optionally filtered by country"""
    try:
        skill = request.args.get('skill', '')
        country = request.args.get('country', 'ALL')
        if not skill:
            return jsonify({"error": "skill param required"}), 400
        data = TrendsService.get_skill_timeline(skill=skill, country=country)
        return jsonify(data), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


