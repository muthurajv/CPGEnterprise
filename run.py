"""Local dev entry point — loads .env and starts the FastAPI app."""
import os
from pathlib import Path

# Load .env before importing anything else
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.api.main:app",
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=int(os.environ.get("APP_PORT", 8000)),
        reload=True,
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )
