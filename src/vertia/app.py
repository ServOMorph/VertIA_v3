from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vertia import __version__
from vertia.config import Settings
from vertia.core.db import Database
from vertia.core.events import EventBus
from vertia.web import pages, system

PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass
class Services:
    settings: Settings
    db: Database
    events: EventBus


def build_services(settings: Settings) -> Services:
    db = Database(settings.database)
    db.initialize()
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    return Services(settings=settings, db=db, events=EventBus())


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    services = build_services(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="VertIA", version=__version__, lifespan=lifespan)
    app.state.services = services
    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    app.include_router(pages.router)
    app.include_router(system.router, prefix="/api")
    return app
