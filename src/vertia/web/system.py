from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from vertia import __version__
from vertia.web.deps import services

router = APIRouter()

UI_PREFERENCE_KEY = "ui"
UI_DEFAULTS = {"panels": {"chat": True, "fichiers": True, "memoire": False, "outils": False}}


class UiPreferences(BaseModel):
    panels: dict[str, bool]


@router.get("/sante")
def sante(svc=Depends(services)) -> dict:
    return {"statut": "ok", "version": __version__, "clients_sse": svc.events.subscriber_count}


@router.get("/events")
async def events(svc=Depends(services)) -> StreamingResponse:
    return StreamingResponse(
        svc.events.subscribe(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/preferences/ui")
def get_ui_preferences(svc=Depends(services)) -> dict:
    raw = svc.db.get_preference(UI_PREFERENCE_KEY)
    if raw is None:
        return UI_DEFAULTS
    return json.loads(raw)


@router.put("/preferences/ui")
def put_ui_preferences(prefs: UiPreferences, svc=Depends(services)) -> dict:
    unknown = set(prefs.panels) - set(UI_DEFAULTS["panels"])
    if unknown:
        raise HTTPException(422, f"Panneaux inconnus : {', '.join(sorted(unknown))}")
    value = prefs.model_dump()
    svc.db.set_preference(UI_PREFERENCE_KEY, json.dumps(value))
    svc.events.publish("preferences.ui", value)
    return value
