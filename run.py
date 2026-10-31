"""Lance VertIA : serveur avec rechargement automatique puis ouverture de l'interface."""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import uvicorn  # noqa: E402

from vertia.config import Settings  # noqa: E402


def wait_port(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.3)
    return False


def open_when_ready(url: str, host: str, port: int) -> None:
    if wait_port(host, port):
        webbrowser.open(url)
    else:
        print(f"Le serveur ne répond pas sur {url}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lancer VertIA")
    parser.add_argument("--no-browser", action="store_true", help="ne pas ouvrir le navigateur")
    parser.add_argument("--no-reload", action="store_true", help="désactiver le rechargement auto")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not args.no_browser:
        threading.Thread(
            target=open_when_ready, args=(settings.url, settings.host, settings.port), daemon=True
        ).start()
    print(f"VertIA : {settings.url}  (Ctrl+C pour arrêter)")
    uvicorn.run(
        "vertia.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        reload=not args.no_reload,
        reload_dirs=[str(SRC)],
        reload_includes=["*.py", "*.html", "*.css", "*.js"],
        app_dir=str(SRC),
        log_level="info",
    )


if __name__ == "__main__":
    main()
