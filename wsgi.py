"""
WSGI entry point for production deployment
Run with: gunicorn wsgi:app
"""

import os
from app import create_app

# Create Flask application
app = create_app(config_name=os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    # For development only
    app.run(host="0.0.0.0", port=5001, debug=False)
