"""Render startup with error diagnostics."""
import os
import sys
import traceback

port = int(os.environ.get("PORT", 10000))
print(f"Python {sys.version}", flush=True)
print(f"PORT={port}", flush=True)

try:
    print("Importing src.main...", flush=True)
    from src.main import app
    print("Import OK — starting uvicorn...", flush=True)
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=port)
except Exception as e:
    print(f"FATAL: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()
    sys.exit(1)
