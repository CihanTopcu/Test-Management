"""DGTest API -- DGPays yazilim test yonetimi."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import bootstrap

from .config import get_settings
from . import ratelimit
from .ratelimit import RateLimitMiddleware
from .api.routers import (admin, attachments, auth, automation, autotest, cases,
                          catalog, importer, jira, overview, plans, reports,
                          runs, search, workspace)

settings = get_settings()

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # a fresh container comes up against an empty database; create the schema
    # and an administrator so the first page load is a login screen and not a
    # stack trace
    bootstrap.run()
    from .autotest import schedule
    schedule.start()
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="TestRail yerine gecen kendi test yonetim sistemimiz",
    lifespan=lifespan,
)

# added before CORS so that a 429 still carries the CORS headers the browser
# needs to read it
ratelimit.ENABLED = settings.rate_limit_enabled
app.add_middleware(RateLimitMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, catalog, overview, cases, runs, plans, reports,
               admin, automation, search, workspace, attachments, importer,
               jira, autotest):
    app.include_router(module.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name}
