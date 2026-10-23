# Build from repository root: docker build -f backend/Dockerfile -t rent-backend .
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd --uid 10001 --create-home appuser
COPY backend/__init__.py ./backend/__init__.py
COPY machine/analyze.py machine/compare_rent.py machine/normalize_listing.py ./machine/
COPY machine/integration_kit_v1.1/ ./machine/integration_kit_v1.1/
COPY machine/analysis_internal/ ./machine/analysis_internal/
COPY backend/app/ ./backend/app/
COPY backend/scripts/ ./backend/scripts/
COPY backend/web/ ./backend/web/
RUN mkdir -p backend/data && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=8s --start-period=60s --retries=3 CMD ["python", "-m", "backend.scripts.healthcheck"]
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
