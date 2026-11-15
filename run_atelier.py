"""Lance l'éditeur local Atelier."""
import argparse
import os
import socket
import sys
import threading
import time
import webbrowser

import uvicorn

from modules.atelier.serveur import app


def ouvrir_quand_pret(port: int) -> None:
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                webbrowser.open(f"http://127.0.0.1:{port}")
                return
        except OSError:
            time.sleep(0.3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lancer Atelier")
    parser.add_argument("--port", type=int, default=os.environ.get("ATELIER_PORT", "4320"))
    parser.add_argument("--sans-navigateur", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.port == 4310:
        parser.error("Port invalide : choisir 1 à 65535, sauf 4310 (portail)")
    # Garder le socket réservé ferme la course entre le contrôle et uvicorn.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", args.port))
            sock.listen(128)
        except OSError:
            print(f"Lancement annulé : port {args.port} occupé ou indisponible.", file=sys.stderr)
            raise SystemExit(1) from None
        if not args.sans_navigateur:
            threading.Thread(target=ouvrir_quand_pret, args=(args.port,), daemon=True).start()
        serveur = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port))
        serveur.run(sockets=[sock])


if __name__ == "__main__":
    main()
