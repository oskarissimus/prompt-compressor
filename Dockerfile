# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install uv
RUN pip install uv

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY proxy.py ./

# Expose port (Cloud Run will set PORT env var)
EXPOSE 8080

# Set default port for Cloud Run
ENV PORT=8080

# Run the FastAPI application
CMD ["uv", "run", "uvicorn", "proxy:app", "--host", "0.0.0.0", "--port", "8080"] 