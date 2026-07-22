# StockPilot API — production image.
#
# Python 3.12 (matches the version documented in agent/DOCUMENTATION.md §2).
# Slim base: pandas/numpy/asyncpg/psycopg2-binary all ship manylinux wheels for
# 3.12, so no compiler toolchain is needed in the image.
FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE — no .pyc clutter in the image layer.
# PYTHONUNBUFFERED     — log lines reach `docker compose logs` immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Warsaw

WORKDIR /app

# Dependencies first: this layer is rebuilt only when requirements.txt changes,
# so ordinary code deploys reuse the cached wheel install.
COPY requirements.txt ./
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

# Application code (alembic/ is included so migrations can be run manually with
# `docker compose exec api alembic upgrade head` on managed deployments).
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./

# Run as a non-root user — a container break-out lands on an unprivileged account.
RUN useradd --create-home --uid 10001 stockpilot && chown -R stockpilot:stockpilot /app
USER stockpilot

EXPOSE 5111

# Liveness probe used by docker compose (`depends_on: condition: service_healthy`).
# urllib instead of curl so the image needs no extra packages.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:5111/health', timeout=4).status == 200 else 1)"

# IMPORTANT — exactly ONE worker process.
#
# The app keeps state inside the process: the APScheduler nightly job (18:00
# Europe/Warsaw), the in-process history/ranking TTL caches, and the refresh
# service's status. A second worker would run a second scheduler (duplicate
# Yahoo pulls, duplicate DB writes) and hold its own cache, so two identical
# requests could return different rankings. Scale up with a bigger VPS, not
# with more workers, until that state is moved out of the process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5111", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
