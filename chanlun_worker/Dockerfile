FROM python:3.11.14-slim-bookworm AS dependencies
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
WORKDIR /app
COPY chanlun_worker/requirements-base.lock /app/requirements-base.lock
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements-base.lock
RUN useradd --uid 10001 --no-create-home app

FROM dependencies AS czsc-dependencies
COPY chanlun_worker/requirements-czsc.lock /app/requirements-czsc.lock
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements-czsc.lock

FROM dependencies AS chanpy
COPY chanlun_worker /app/chanlun_worker
COPY docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz /app/docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz
COPY third_party/chanpy /app/third_party/chanpy
ENV CHANLUN_ENGINE=chanpy
USER 10001:10001
CMD ["uvicorn", "chanlun_worker.app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]

FROM dependencies AS native
COPY chanlun_worker /app/chanlun_worker
COPY docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz /app/docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz
ENV CHANLUN_ENGINE=native
USER 10001:10001
CMD ["uvicorn", "chanlun_worker.app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]

FROM dependencies AS baseline
COPY chanlun_worker /app/chanlun_worker
COPY docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz /app/docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz
COPY backtesting/chanlun_research.py /app/backtesting/chanlun_research.py
ENV CHANLUN_ENGINE=baseline
USER 10001:10001
CMD ["uvicorn", "chanlun_worker.app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]

FROM czsc-dependencies AS czsc
COPY chanlun_worker /app/chanlun_worker
COPY docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz /app/docs/research/data/fu-chanlun-2026-10-30/source-snapshot.json.gz
ENV CHANLUN_ENGINE=czsc
USER 10001:10001
CMD ["uvicorn", "chanlun_worker.app:app", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
