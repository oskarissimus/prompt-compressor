#!/usr/bin/env python3
"""
Basic transparent proxy to OpenAI API
Forwards all requests from http://localhost:8000 to https://api.openai.com
"""

import os
import json
import logging
import random
from typing import Any, Dict, Optional
from datetime import datetime
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import uvicorn
import tiktoken

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

# Create separate logger for compression logging
compression_logger = logging.getLogger('compression')
compression_logger.setLevel(logging.INFO)
compression_logger.propagate = False

# Only add handler if it doesn't already exist (prevents duplicate logs)
if not compression_logger.handlers:
    compression_file_handler = logging.FileHandler('compression.log')
    compression_file_handler.setLevel(logging.INFO)
    compression_formatter = logging.Formatter('%(asctime)s - %(message)s')
    compression_file_handler.setFormatter(compression_formatter)
    compression_logger.addHandler(compression_file_handler)

# OpenAI API configuration
OPENAI_BASE_URL = "https://api.openai.com/v1"

# Compression configuration
COMPRESSION_RATIO = float(os.getenv("COMPRESSION_RATIO", "1.0"))  # Default no compression

def compress_text(text: str, compression_ratio: float) -> str:
    """
    Simple token-based compression algorithm.
    Removes N random tokens where N = token_count * (1 - 1/compression_ratio)
    """
    if compression_ratio <= 1.0:
        return text  # No compression needed
    
    try:
        # Use cl100k_base encoding (GPT-4/GPT-3.5-turbo)
        encoding = tiktoken.get_encoding("cl100k_base")
        
        # Tokenize the text
        tokens = encoding.encode(text)
        token_count = len(tokens)
        
        if token_count == 0:
            return text
        
        # Calculate how many tokens to remove
        tokens_to_remove = int(token_count * (1 - 1/compression_ratio))
        
        if tokens_to_remove <= 0:
            return text
        
        # Randomly select tokens to remove
        indices_to_remove = set(random.sample(range(token_count), min(tokens_to_remove, token_count)))
        
        # Create new token list without the removed tokens
        compressed_tokens = [token for i, token in enumerate(tokens) if i not in indices_to_remove]
        
        # Decode back to text
        compressed_text = encoding.decode(compressed_tokens)
        
        # Ensure the compressed text is valid
        if not compressed_text.strip():
            logger.warning("Compression resulted in empty text, returning original")
            return text
        
        logger.info(f"Compressed text: {token_count} -> {len(compressed_tokens)} tokens (removed {tokens_to_remove})")
        
        # Log compression details to separate file
        compression_logger.info("=" * 80)
        compression_logger.info(f"COMPRESSION APPLIED - Ratio: {compression_ratio}")
        compression_logger.info(f"Original tokens: {token_count}")
        compression_logger.info(f"Compressed tokens: {len(compressed_tokens)}")
        compression_logger.info(f"Removed tokens: {tokens_to_remove}")
        compression_logger.info(f"Compression percentage: {100 * tokens_to_remove / token_count:.1f}%")
        compression_logger.info("-" * 40 + " BEFORE " + "-" * 40)
        compression_logger.info(text)
        compression_logger.info("-" * 40 + " AFTER " + "-" * 41)
        compression_logger.info(compressed_text)
        compression_logger.info("=" * 80)
        compression_logger.info("")
        
        return compressed_text
        
    except Exception as e:
        logger.warning(f"Compression failed: {e}, returning original text")
        return text

def compress_chat_messages(messages: list, compression_ratio: float) -> list:
    """
    Apply compression to chat messages, focusing on user messages
    """
    if compression_ratio <= 1.0:
        return messages
    
    compressed_messages = []
    user_message_count = 0
    
    for i, message in enumerate(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content", "")
            if isinstance(content, str):
                user_message_count += 1
                compression_logger.info(f"COMPRESSING USER MESSAGE #{user_message_count} (position {i})")
                compressed_content = compress_text(content, compression_ratio)
                compressed_message = message.copy()
                compressed_message["content"] = compressed_content
                compressed_messages.append(compressed_message)
            else:
                compressed_messages.append(message)
        else:
            compressed_messages.append(message)
    
    if user_message_count > 0:
        compression_logger.info(f"COMPRESSION SUMMARY: Processed {user_message_count} user messages")
    
    return compressed_messages

# Create HTTP client for forwarding requests
client = httpx.AsyncClient(timeout=300.0)

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    yield
    # Shutdown
    await client.aclose()

app = FastAPI(title="OpenAI Proxy", description="Transparent proxy to OpenAI API", lifespan=lifespan)

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy", "proxy_target": OPENAI_BASE_URL}

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
        original_body_data = None
        if request.method in ["POST", "PUT", "PATCH"]:
            body = await request.body()
            
            # Apply compression for chat completions
            if body and path.endswith("chat/completions") and COMPRESSION_RATIO > 1.0:
                try:
                    body_str = body.decode('utf-8')
                    body_data = json.loads(body_str)
                    if "messages" in body_data and isinstance(body_data["messages"], list):
                        original_body_data = body_data.copy()
                        compression_logger.info(f"NEW CHAT COMPLETION REQUEST - Timestamp: {datetime.now().isoformat()}")
                        compression_logger.info(f"Target URL: {target_url}")
                        compression_logger.info(f"Compression ratio: {COMPRESSION_RATIO}")
                        compression_logger.info("")
                        
                        body_data["messages"] = compress_chat_messages(body_data["messages"], COMPRESSION_RATIO)
                        new_body_str = json.dumps(body_data, ensure_ascii=False)
                        body = new_body_str.encode('utf-8')
                        logger.info(f"Applied compression ratio {COMPRESSION_RATIO} to chat completion request")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON for compression: {e}")
                except UnicodeDecodeError as e:
                    logger.warning(f"Failed to decode body for compression: {e}")
                except Exception as e:
                    logger.warning(f"Failed to apply compression: {e}")
                    import traceback
                    logger.warning(f"Compression error traceback: {traceback.format_exc()}")
        
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

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting OpenAI proxy server on {host}:{port}")
    logger.info(f"Forwarding requests to {OPENAI_BASE_URL}")
    if COMPRESSION_RATIO > 1.0:
        logger.info(f"Compression enabled with ratio {COMPRESSION_RATIO} (removes ~{100*(1-1/COMPRESSION_RATIO):.1f}% of tokens)")
    else:
        logger.info("Compression disabled")
    
    uvicorn.run(
        "proxy:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    ) 