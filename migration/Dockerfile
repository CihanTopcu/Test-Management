# TestRail sync worker.
#
# Temporary by design: it exists only while TestRail and this instance are
# both alive. When TestRail is shut down, set TESTRAIL_SYNC_ENABLED=false or
# remove the service -- nothing else in the stack depends on it.
#
# It carries the migration tools and the application's models, because the
# loader writes through the same SQLAlchemy models the API uses. Sharing the
# models is the point: a sync that wrote rows its own way would drift from
# the application's idea of them.
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential libpq-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /wheels
COPY backend/requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt requests


FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/srv/backend:/srv/migration

RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=build /wheels /wheels
COPY backend/requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt requests \
 && rm -rf /wheels requirements.txt

RUN useradd --create-home --uid 10002 sync

WORKDIR /srv
COPY --chown=sync:sync backend/app ./backend/app
COPY --chown=sync:sync migration ./migration

# the dump tree is a volume: it is 1.6 GB and belongs to the host, not here
RUN mkdir -p /srv/data && chown sync:sync /srv/data

USER sync

# One pass per interval, forever. State lives in the database, so a restart
# resumes rather than repeats.
CMD ["python", "migration/sync.py", "--loop"]
