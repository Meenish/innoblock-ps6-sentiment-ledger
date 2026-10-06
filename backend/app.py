"""Entry point. Locally: python app.py   On Render: gunicorn app:app --timeout 120"""
import os

from api import create_app

app = create_app()

if __name__ == "__main__":
    app.run(port=int(os.getenv("PORT", "5000")), debug=True, use_reloader=False)
