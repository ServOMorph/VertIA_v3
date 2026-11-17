from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from vertia import __version__
from vertia.chemins import ROOT

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")


@router.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {"version": __version__})


@router.get('/voix')
def voix():
    return FileResponse(ROOT / 'modules/voix/static/voix.html', media_type='text/html')


@router.get('/musique')
def musique():
    return FileResponse(ROOT / 'modules/musique/static/musique.html', media_type='text/html')


@router.get('/video')
def video():
    return FileResponse(ROOT / 'modules/video/static/video.html', media_type='text/html')
