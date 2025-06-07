# OpenAI API Proxy

A FastAPI-based transparent proxy to the OpenAI API with optional token compression. Can be deployed locally or to Google Cloud Run for production use.

## Features

- **Transparent Proxy**: Forwards all requests to OpenAI API while preserving headers, streaming, and error handling
- **Token Compression**: Optionally reduces token usage by randomly removing tokens from user messages
- **Production Ready**: Designed for deployment to Google Cloud Run with automatic CI/CD
- **Comprehensive Logging**: Detailed request/response and compression activity logging
- **Health Monitoring**: Built-in health check endpoint
- **Streaming Support**: Full support for streaming chat completions

## Quick Deployment to Cloud Run

See [DEPLOYMENT_SETUP.md](DEPLOYMENT_SETUP.md) for detailed setup instructions.

**Quick steps:**
1. Fork this repository
2. Set up Google Cloud project and service account
3. Add secrets to GitHub repository (`GCP_PROJECT_ID`, `GCP_SA_KEY`, optional `COMPRESSION_RATIO`)
4. Push to main branch - automatic deployment via GitHub Actions

## Local Development

### Quick Start

```bash
# Install dependencies
uv sync

# Set your API key and run
export OPENAI_API_KEY="your-api-key-here"
uv run python proxy.py
```

Or use the helper script:
```bash
# Edit run.sh to set your API key, then:
./run.sh
```

### With Docker

```bash
# Build and run
docker build -t openai-proxy .
docker run -p 8080:8080 -e OPENAI_API_KEY="your-key" openai-proxy

# Test health endpoint
curl http://localhost:8080/health
```

### With Compression

```bash
# Run with 2x compression (removes ~50% of tokens from user messages)
export COMPRESSION_RATIO=2.0
export OPENAI_API_KEY="your-api-key-here"
uv run python proxy.py

# Or with 3x compression (removes ~67% of tokens)
export COMPRESSION_RATIO=3.0
uv run python proxy.py
```

## Usage Examples

Once running (locally on port 8000 or deployed to Cloud Run), use as a drop-in replacement for the OpenAI API:

### Local Usage
```bash
curl -X POST "http://localhost:8000/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_OPENAI_API_KEY" \
  -d '{
    "model": "gpt-3.5-turbo",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### Cloud Run Usage
```bash
curl -X POST "https://your-service-url.run.app/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_OPENAI_API_KEY" \
  -d '{
    "model": "gpt-3.5-turbo", 
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

### With Open WebUI

```bash
# For local proxy (port 8000)
docker run --rm -p 3000:8080 \
  -e OPENAI_API_KEY="your-openai-api-key-here" \
  -e OPENAI_API_BASE_URL=http://localhost:8000 \
  -v open-webui:/app/backend/data \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main

# For deployed proxy
docker run --rm -p 3000:8080 \
  -e OPENAI_API_KEY="your-openai-api-key-here" \
  -e OPENAI_API_BASE_URL=https://your-service-url.run.app \
  -v open-webui:/app/backend/data \
  --name open-webui \
  ghcr.io/open-webui/open-webui:main
```

## Configuration

### Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key (required for local development)
- `COMPRESSION_RATIO`: Token compression ratio (default: 1.0)
  - `1.0`: No compression (default)
  - `2.0`: Removes ~50% of tokens from user messages
  - `3.0`: Removes ~67% of tokens from user messages
  - `4.0`: Removes ~75% of tokens from user messages
- `PORT`: Port to run on (default: 8000 locally, 8080 for Cloud Run)
- `HOST`: Host to bind to (default: 0.0.0.0)

### Compression Details

The compression algorithm:
1. Only affects user messages in chat completions
2. Uses random token removal to maintain semantic diversity
3. Preserves message structure and role assignments
4. Logs detailed before/after comparisons
5. Falls back gracefully if compression fails

## Monitoring and Logs

### Local Development
- `proxy_requests.log`: Request/response logging
- `compression.log`: Detailed compression activity with before/after text

### Cloud Run Production
- View logs: `gcloud run services logs read openai-proxy --region=us-central1`
- Monitor metrics in Google Cloud Console
- Set up alerting for errors or performance issues

## Architecture

### Local Development
```
Client → FastAPI (localhost:8000) → OpenAI API
```

### Production (Cloud Run)
```
Client → Cloud Run Service → OpenAI API
         ↓
    Container Registry
         ↓  
    GitHub Actions CI/CD
```

## Development

The proxy is built with:
- **FastAPI**: Modern, fast web framework with automatic OpenAPI docs
- **httpx**: Async HTTP client for forwarding requests
- **tiktoken**: OpenAI's tokenizer for compression calculations
- **uvicorn**: ASGI server for production deployment

### Project Structure
```
├── proxy.py              # Main FastAPI application
├── main.py               # Legacy Cloud Functions entry (deprecated)
├── Dockerfile            # Container image definition
├── pyproject.toml        # Python dependencies (uv format)
├── .github/workflows/    # CI/CD pipeline
└── DEPLOYMENT_SETUP.md   # Detailed deployment guide
```

### Adding Features

The modular design makes it easy to extend:
- Add new compression algorithms in `compress_text()`
- Implement custom authentication middleware
- Add request/response transformations
- Integrate with monitoring services

## Contributing

1. Fork the repository
2. Create a feature branch
3. Test locally with `uv run python proxy.py`
4. Submit a pull request

## License

MIT License - feel free to use and modify for your needs. 