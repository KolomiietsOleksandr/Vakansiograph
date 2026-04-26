"""
LABO — Labor Market Intelligence API
Flask application factory pattern
"""

from flask import Flask, render_template
from flask_cors import CORS
from app.config import Config, DevelopmentConfig
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app(config_name: str = "development"):
    """Create and configure Flask application"""
    app = Flask(__name__)

    # Load config
    if config_name == "production":
        from app.config import ProductionConfig
        app.config.from_object(ProductionConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    # Enable CORS
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Register blueprints
    from app.api.routes import jobs_bp, skills_bp, salaries_bp, locations_bp, categories_bp, trends_bp, health_bp

    app.register_blueprint(jobs_bp)
    app.register_blueprint(skills_bp)
    app.register_blueprint(salaries_bp)
    app.register_blueprint(locations_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(trends_bp)
    app.register_blueprint(health_bp)

    # Frontend routes
    @app.route('/')
    def index():
        """Serve homepage"""
        return render_template('index.html')

    @app.route('/dashboard')
    @app.route('/dashboard.html')
    def dashboard():
        """Serve dashboard"""
        return render_template('dashboard.html')

    @app.route('/countries')
    @app.route('/countries.html')
    def countries_page():
        return render_template('countries.html')

    @app.route('/trends')
    @app.route('/trends.html')
    def trends():
        return render_template('trends.html')

    @app.route('/skills-intelligence')
    @app.route('/skills-intelligence.html')
    def skills_intelligence():
        return render_template('skills_intelligence.html')

    logger.info(f"Flask app created with config: {config_name}")
    return app
