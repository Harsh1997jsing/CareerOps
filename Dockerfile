# Audit finding F12 — no Dockerfile existed; docker-compose.yml only ran
# Postgres. Runs the FastAPI app (app/api/main.py) — the Streamlit
# dashboard this was originally sketched around (memory/phase-4-dashboard.md)
# was removed; there's nothing else to serve.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Migrations are a separate, explicit step (`alembic upgrade head`) run
# before this starts, or by the deployment platform — not baked into the
# container's startup command, so a container restart never silently
# re-runs migrations against a database another replica is also using.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
