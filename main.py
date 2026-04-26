"""
Development entry point
Run with: python main.py
"""

from app import create_app
import threading
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_scheduler():
    """Run scheduler in background thread"""
    try:
        from app.services.scheduler import start_scheduler
        logger.info("Starting scheduler in background thread...")
        start_scheduler()
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

if __name__ == "__main__":
    app = create_app(config_name="development")
    
    # Start scheduler in background thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    
    # Start Flask server
    logger.info("Starting Flask API server...")
    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
