"""Start the scoring API.

- If COLLIDE_API_PORT is set in `.env`, that port is required (exit with hint if busy).
- Otherwise the first free port in 32587–32686 is used.
- The chosen port is written to `.collide-api-port` so Vite can proxy without a restart.
"""
import os
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

PORT_FILE = ROOT / ".collide-api-port"
HOST = "127.0.0.1"
AUTO_PORT_START = 32587
AUTO_PORT_SPAN = 100


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError:
            return False
    return True


def choose_port() -> int:
    explicit = os.environ.get("COLLIDE_API_PORT")
    if explicit:
        p = int(explicit)
        if _port_free(HOST, p):
            return p
        print(f"\n[COLLIDE] Port {p} (COLLIDE_API_PORT) is already in use.\n")
        print("  Fix: close the other terminal/process using that port, or unset COLLIDE_API_PORT")
        print("       in .env to let the API pick a free port automatically.\n")
        print(f"  PowerShell (admin may be required): Get-NetTCPConnection -LocalPort {p}")
        print("    | Select-Object -ExpandProperty OwningProcess | Get-Unique | ForEach-Object { Stop-Process -Id $_ -Force }\n")
        raise SystemExit(1)

    for port in range(AUTO_PORT_START, AUTO_PORT_START + AUTO_PORT_SPAN):
        if _port_free(HOST, port):
            return port

    print(f"\n[COLLIDE] No free port between {AUTO_PORT_START} and {AUTO_PORT_START + AUTO_PORT_SPAN - 1}.\n")
    raise SystemExit(1)


def write_port_file(port: int) -> None:
    PORT_FILE.write_text(str(port), encoding="utf-8")


if __name__ == "__main__":
    import uvicorn

    port = choose_port()
    write_port_file(port)
    reload = "--reload" in sys.argv

    print(f"\n[COLLIDE] API → http://{HOST}:{port}  (port file: {PORT_FILE.name})\n")

    kw: dict = {"host": HOST, "port": port, "reload": reload}
    if reload:
        kw["reload_dirs"] = [str(ROOT)]
    uvicorn.run("backend.main:app", **kw)
