#!/bin/bash
echo "Starting English Buddy..."
cd "$(dirname "$0")"
python -m uvicorn src.buddy.server:app --host 0.0.0.0 --port ${PORT:-8000}
