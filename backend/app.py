"""Entry point. Locally: python app.py   On Render: gunicorn app:app --timeout 120"""
import os

from api import create_app

app = create_app()

if __name__ == "__main__":
    # debug mode lets anyone who finds an error page run code; keep it OFF unless you opt in locally
    app.run(port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1", use_reloader=False)