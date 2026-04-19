"""Vercel root Python entrypoint compatibility shim.

Allows deployments that resolve the Python function from repository root to
still load the FastAPI app from backend.main.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.main import app
