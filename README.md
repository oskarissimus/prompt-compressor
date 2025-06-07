# OpenAI API Proxy

A basic transparent proxy to the OpenAI API that forwards requests from `http://localhost:8000` to `https://api.openai.com`.

## Setup

1. Make sure you have `uv` installed
2. Set your OpenAI API key in the environment or modify `run.sh`
3. Run the proxy server

## Usage

### Quick Start

```bash
# Run the proxy server
./run.sh
```

### Manual Setup

```bash
# Install dependencies
uv sync

# Set your API key
export OPENAI_API_KEY="your-api-key-here"

# Run the proxy
uv run python proxy.py
```

### With Compression

```bash
# Run with 2x compression (removes ~50% of tokens from user messages)
export COMPRESSION_RATIO=2.0
./run.sh

# Or manually:
export OPENAI_API_KEY="your-api-key-here"
export COMPRESSION_RATIO=3.0  # Removes ~67% of tokens
uv run python proxy.py
```

### With Docker WebUI

Once the proxy is running on port 8000, you can start your WebUI with:

```bash
docker run --rm -p 3000:8080 \
  -e OPENAI_API_KEY="your-openai-api-key-here" \
  -e OPENAI_API_BASE_URL=http://localhost:8000 \
  -v open-webui:/app/backend/data \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

## Features

- Transparent proxy to OpenAI API
- **Simple token compression**: Randomly removes tokens from user messages based on compression ratio
  - Creates detailed compression logs in `compression.log` showing before/after text
- Handles streaming responses (chat completions with `stream=True`)
- Proper error handling and logging
- Health check endpoint at `/health`
- Runs on port 8000 by default

## Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key (required)
- `COMPRESSION_RATIO`: Compression ratio for token removal (default: 1.0, no compression)
  - Values > 1.0 enable compression (e.g., 2.0 removes ~50% of tokens, 3.0 removes ~67%)
  - Only applies to user messages in chat completions
- `PORT`: Port to run the proxy on (default: 8000)
- `HOST`: Host to bind to (default: 0.0.0.0)

## Log Files

The proxy creates two log files:

- `proxy_requests.log`: General request/response logging
- `compression.log`: Detailed compression activity showing:
  - Before and after text for each compression
  - Token counts and compression statistics
  - Which user messages were compressed

## Development

This is a basic implementation designed to be extended later. The proxy:

1. Receives requests on port 8000
2. Forwards them to `https://api.openai.com`
3. Adds the proper Authorization header
4. Returns the response back to the client

Perfect for local development and testing with OpenAI-compatible tools. 