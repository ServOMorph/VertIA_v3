from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from vertia import __version__
from vertia.config import Settings
from vertia.chemins import ROOT, Chemins, resoudre_chemins
from vertia.modules.registry import RegistreModules
from vertia.demandes import DemandesService
from vertia.api.v1 import router as api_v1
from vertia.core.db import Database
from vertia.core.events import EventBus
from vertia.chat.repository import ChatRepository
from vertia.chat.service import ChatService
from vertia.chat.orchestrator import Orchestrator
from vertia.engines.comfy_qwen import ComfyQwenEngine
from vertia.engines.video_wan import WanVideoEngine
from vertia.engines.acestep import AceStepEngine
from vertia.engines.ollama import OllamaClient, OllamaEngine
from vertia.engines.ollama_service import OllamaService
from vertia.engines.ollama_preload import OllamaPreload
from vertia.jobs.arbiter import GpuArbiter
from vertia.jobs.queue import JobQueue
from vertia.gpu import VerrouGpu
from vertia.resources.monitor import MemoryGuard, ResourceMonitor
from vertia.tools.registry import ToolRegistry
from vertia.tools.image import ImageTool
from vertia.tools.video import VideoTool
from vertia.tools.music import MusicTool
from vertia.files.store import FileStore
from vertia.web import actions, chat, files, pages, resources, system, setup

PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass
class Services:
    settings: Settings
    db: Database
    events: EventBus
    ollama: OllamaClient
    chat: ChatService
    monitor: ResourceMonitor
    arbiter: GpuArbiter
    jobs: JobQueue
    tools: ToolRegistry
    actions: Orchestrator
    files: FileStore
    ollama_service: OllamaService
    ollama_preload: OllamaPreload
    modules: RegistreModules
    demandes: DemandesService
    chemins: Chemins

    async def watch_resources(self):
        while True:
            try:
                await self.arbiter.release_idle()
                state = dict(await self.monitor.sample(), engine=self.arbiter.active)
                self.events.publish('ressources.maj', state)
            except Exception:
                self.events.publish('ressources.erreur', {'erreur': 'Mesure ou libération mémoire indisponible. Réessayez depuis le panneau Mémoire.'})
            await asyncio.sleep(5)


def build_services(settings: Settings, overrides: dict | None = None) -> Services:
    db = Database(settings.database)
    db.initialize()
    settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    events = EventBus()
    ollama_service = (overrides or {}).get('ollama_service') or OllamaService(
        settings.ollama_url, events, settings.ollama_executable, settings.ollama_autostart)
    ollama = (overrides or {}).get('ollama') or OllamaClient(settings.ollama_url, settings.num_ctx)
    monitor = (overrides or {}).get('monitor') or ResourceMonitor(ollama)
    comfy = (overrides or {}).get('engines', {}).get('comfy') or ComfyQwenEngine(settings.comfy_dir, settings.comfy_port)
    ace = (overrides or {}).get('engines', {}).get('ace') or AceStepEngine(settings.acestep_dir, settings.acestep_port)
    engines = {'ollama': OllamaEngine(ollama), 'comfy': comfy, 'ace': ace,
               **(overrides or {}).get('engines', {})}
    verrou = (overrides or {}).get('verrou_gpu')
    if verrou is None and settings.verrou_gpu:
        verrou = VerrouGpu(settings.verrou_gpu_attente_s)
    arbiter = GpuArbiter(engines, MemoryGuard(monitor, settings.vram_limit_percent, settings.ram_limit_percent,
                                          settings.resident_vram_reserve_mb), settings.engine_idle_seconds, verrou)
    jobs = JobQueue(db, arbiter, events)
    ollama_preload = OllamaPreload(ollama_service, ollama, jobs, settings.default_model)
    for kind, handler in (overrides or {}).get('job_handlers', {}).items():
        jobs.register(kind, handler)
    chat_service = ChatService(ChatRepository(db), ollama, events, settings.num_ctx, jobs)
    tools = ToolRegistry(engines)
    file_store = FileStore(db, chat_service.repository, settings.outputs_dir, events)
    tools.register(ImageTool(engines['comfy'], file_store))
    tools.register(VideoTool(WanVideoEngine(engines['comfy']), file_store))
    tools.register(MusicTool(engines['ace']))
    for tool in (overrides or {}).get('tools', []):
        tools.register(tool)
    actions_service = Orchestrator(db, chat_service.repository, tools, jobs, events, file_store)
    chat_service.orchestrator = actions_service
    chemins = (overrides or {}).get('chemins') or resoudre_chemins()
    modules = (overrides or {}).get('modules') or RegistreModules()
    demandes = DemandesService(db, jobs, modules, settings, chemins)
    return Services(settings=settings, db=db, events=events, ollama=ollama, chat=chat_service,
                    monitor=monitor, arbiter=arbiter, jobs=jobs, tools=tools, actions=actions_service, files=file_store,
                    ollama_service=ollama_service, ollama_preload=ollama_preload,
                    modules=modules, demandes=demandes, chemins=chemins)


def create_app(settings: Settings | None = None, overrides: dict | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    services = build_services(settings, overrides)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services.ollama_service.start_background()
        if settings.preload_ollama:
            services.ollama_preload.start()
        services.jobs.start()
        watcher = asyncio.create_task(services.watch_resources())
        try:
            yield
        finally:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)
            try:
                await services.ollama_preload.close()
                await services.jobs.close()
                await services.demandes.close()
                await services.arbiter.close()
                await services.chat.close()
                services.actions.ephemeral.clear()
                services.files.ephemeral.clear()
                for engine in services.arbiter.engines.values():
                    if hasattr(engine, 'close'):
                        await engine.close()
            finally:
                try:
                    await services.jobs.close()
                finally:
                    try:
                        await services.arbiter.close()
                    finally:
                        await services.ollama_service.close()

    app = FastAPI(title="VertIA", version=__version__, lifespan=lifespan)
    app.state.services = services

    @app.middleware('http')
    async def refresh_interface(request, call_next):
        response = await call_next(request)
        if request.url.path == '/' or request.url.path.startswith(('/static/js/', '/static/css/')):
            response.headers['Cache-Control'] = 'no-cache'
        return response

    app.mount("/static", StaticFiles(directory=PACKAGE_DIR / "static"), name="static")
    app.mount('/modules/voix/static', StaticFiles(directory=ROOT / 'modules/voix/static'), name='voix_static')
    app.include_router(pages.router)
    app.include_router(system.router, prefix="/api")
    app.include_router(setup.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(resources.router, prefix="/api")
    app.include_router(actions.router, prefix="/api")
    app.include_router(files.router, prefix="/api")
    app.include_router(api_v1)
    return app
