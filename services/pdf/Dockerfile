FROM python:3.12-slim

WORKDIR /app

# weasyprint requires pango + cairo for HTML→PDF rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libfontconfig1 \
    fontconfig \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py render.py ./
COPY templates/ ./templates/

# Fonts mounted at runtime via volume (./fonts:/app/fonts in docker-compose)
ENV CAREER_AGENT_FONTS=/app/fonts

EXPOSE 8002

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
