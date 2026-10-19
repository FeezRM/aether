#!/usr/bin/env bash
# Start LocalPDF Studio: one local process serving the API and the built UI on 127.0.0.1.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x backend/.venv/bin/python ]; then
  python3 -m venv backend/.venv
fi
# (Re)install when the venv is new or predates the local AI runtime.
if ! backend/.venv/bin/python -c "import fastapi, llama_cpp" 2>/dev/null; then
  # Prebuilt llama.cpp wheels (Metal on Apple Silicon, CPU elsewhere) so no compiler is needed;
  # pip falls back to building from source if no wheel matches.
  if [ "$(uname -s)" = "Darwin" ]; then WHEELS=metal; else WHEELS=cpu; fi
  backend/.venv/bin/pip install -q -r backend/requirements.txt \
    --extra-index-url "https://abetlen.github.io/llama-cpp-python/whl/${WHEELS}"
fi
if [ ! -f frontend/dist/index.html ]; then
  npm --prefix frontend install
  npm --prefix frontend run build
fi

PORT="${LOCALPDF_PORT:-8765}"
echo "LocalPDF Studio: http://127.0.0.1:${PORT}  (documents never leave this computer)"
exec backend/.venv/bin/python -m uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port "$PORT"
