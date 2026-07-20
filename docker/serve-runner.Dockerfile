# Minimal inference runner for Perzforge serving contract v1.
# See docs/SERVING.md.
FROM python:3.12-slim

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin app \
    && pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.8"

WORKDIR /app
COPY docker/serve-runner/loader.py /app/loader.py

USER 1000:1000
EXPOSE 8000

CMD ["uvicorn", "loader:app", "--host", "0.0.0.0", "--port", "8000"]
