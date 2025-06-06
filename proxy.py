#!/usr/bin/env python3
"""
Basic transparent proxy to OpenAI API
Forwards all requests from http://localhost:8000 to https://api.openai.com
"""

import os
import json
import logging
from typing import Any, Dict, Optional
from datetime import datetime
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure file logging for requests/responses
file_handler = logging.FileHandler('proxy_requests.log')
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(message)s')
file_handler.setFormatter(file_formatter)

# Create separate logger for request/response logging
request_logger = logging.getLogger('proxy_requests')
request_logger.setLevel(logging.INFO)
request_logger.addHandler(file_handler)
request_logger.propagate = False

# OpenAI API configuration
OPENAI_BASE_URL = "https://api.openai.com/v1"

app = FastAPI(title="OpenAI Proxy", description="Transparent proxy to OpenAI API")

# Create HTTP client for forwarding requests
client = httpx.AsyncClient(timeout=300.0)

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy_request(request: Request, path: str):
    """
    Transparent proxy endpoint that forwards all requests to OpenAI API
    """
    try:
        # Build target URL
        target_url = f"{OPENAI_BASE_URL}/{path}"
        
        # Get request body if present
        body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.body()
        
        # Prepare headers
        headers = dict(request.headers)
        
        # Remove host header to avoid conflicts
        headers.pop("host", None)
        
        # Log incoming request
        request_data = {
            "timestamp": datetime.now().isoformat(),
            "direction": "REQUEST",
            "method": request.method,
            "url": target_url,
            "headers": {k: v for k, v in headers.items() if k.lower() not in ['authorization']},  # Mask auth header
            "query_params": dict(request.query_params),
            "body_size": len(body) if body else 0
        }
        
        # Log body for small requests (avoid logging huge files)
        if body and len(body) < 10000:
            try:
                request_data["body"] = body.decode('utf-8')
            except:
                request_data["body"] = f"<binary data, {len(body)} bytes>"
        
        request_logger.info(f"REQUEST: {json.dumps(request_data, indent=2)}")
        
        # Forward the request
        logger.info(f"Forwarding {request.method} {target_url}")
        
        response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=request.query_params,
            content=body
        )
        
        # Log response metadata
        response_data = {
            "timestamp": datetime.now().isoformat(),
            "direction": "RESPONSE",
            "status_code": response.status_code,
            "headers": {k: v for k, v in response.headers.items() if k.lower() not in ['authorization']},
            "content_length": len(response.content) if response.content else 0,
            "is_streaming": response.headers.get("content-type", "").startswith("text/event-stream")
        }
        
        # Handle streaming responses (like chat completions with stream=True)
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            request_logger.info(f"RESPONSE: {json.dumps(response_data, indent=2)}")
            
            # For streaming, we need to log chunks as they come
            async def log_streaming_response():
                chunk_count = 0
                async for chunk in response.aiter_bytes():
                    chunk_count += 1
                    if chunk_count <= 5:  # Log first few chunks
                        try:
                            chunk_text = chunk.decode('utf-8')
                            request_logger.info(f"STREAM_CHUNK_{chunk_count}: {chunk_text.strip()}")
                        except:
                            request_logger.info(f"STREAM_CHUNK_{chunk_count}: <binary data, {len(chunk)} bytes>")
                    yield chunk
                request_logger.info(f"STREAM_END: Total chunks: {chunk_count}")
            
            return StreamingResponse(
                log_streaming_response(),
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="text/event-stream"
            )
        
        # Handle regular responses
        # Log response body for small responses
        if response.content and len(response.content) < 10000:
            try:
                response_data["body"] = response.content.decode('utf-8')
            except:
                response_data["body"] = f"<binary data, {len(response.content)} bytes>"
        
        request_logger.info(f"RESPONSE: {json.dumps(response_data, indent=2)}")
        
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers)
        )
        
    except httpx.RequestError as e:
        logger.error(f"Request error: {e}")
        raise HTTPException(status_code=502, detail="Bad Gateway - Failed to connect to OpenAI API")
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy", "proxy_target": OPENAI_BASE_URL}

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    await client.aclose()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting OpenAI proxy server on {host}:{port}")
    logger.info(f"Forwarding requests to {OPENAI_BASE_URL}")
    
    uvicorn.run(
        "proxy:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    ) 