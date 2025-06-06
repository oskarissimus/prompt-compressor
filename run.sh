#!/bin/bash

# Run the proxy server with dependencies
echo "Starting OpenAI proxy server on port 8000..."
uv run --no-project --with fastapi --with uvicorn --with httpx --with python-multipart python proxy.py 