"""Render startup with error diagnostics.

If the full app import fails, starts a minimal diagnostic server
so the deploy succeeds and logs are visible.
"""
import os
import sys
import traceback

port = int(os.environ.get("PORT", 10000))
print(f"Python {sys.version}", flush=True)
print(f"PORT={port}", flush=True)

startup_error = None

try:
    print("Importing src.main...", flush=True)
    from src.main import app
    print("Import OK — starting uvicorn...", flush=True)
except Exception as e:
    startup_error = traceback.format_exc()
    print(f"FATAL: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()

    # Build a minimal diagnostic app so Render keeps the service alive
    from fastapi import FastAPI
    app = FastAPI(title="WASI Diagnostic Mode")

    @app.get("/api/health")
    def health():
        return {"status": "error", "mode": "diagnostic", "error": str(e)}

    @app.get("/api/diagnostic/error")
    def full_error():
        return {"traceback": startup_error}

import uvicorn
uvicorn.run(app, host="0.0.0.0", port=port)
