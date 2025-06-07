#!/bin/bash

# Run the proxy server with dependencies
echo "Starting OpenAI proxy server on port 8000..."
if [ -n "$COMPRESSION_RATIO" ] && [ "$COMPRESSION_RATIO" != "1.0" ]; then
    echo "Compression enabled with ratio: $COMPRESSION_RATIO"
fi
uv run --no-project --with fastapi --with uvicorn --with httpx --with python-multipart --with tiktoken python proxy.py 