# 저장소 루트에서: docker build -f backend/Dockerfile -t rent-backend .
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd --create-home appuser
COPY analyze.py compare_rent.py normalize_listing.py ./
COPY integration_kit_v1.1/ ./integration_kit_v1.1/
COPY backend/app/ ./backend/app/
RUN mkdir -p backend/data && chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
