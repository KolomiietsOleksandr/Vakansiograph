import os
from app import create_app

app = create_app(config_name=os.getenv("FLASK_ENV", "production"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
