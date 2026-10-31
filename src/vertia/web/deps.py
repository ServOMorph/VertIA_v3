from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request

if TYPE_CHECKING:
    from vertia.app import Services


def services(request: Request) -> "Services":
    return request.app.state.services
