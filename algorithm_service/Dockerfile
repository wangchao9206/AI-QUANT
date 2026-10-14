FROM python:3.12.10-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app algorithm_service algorithm_service
COPY --chown=app:app config config
COPY --chown=app:app data data
COPY --chown=app:app engines engines
RUN mkdir -p /var/lib/aiquant/feed && chown app:app /var/lib/aiquant/feed
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "algorithm_service.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
