#!/usr/bin/env python3
"""
Google Cloud Functions entry point for OpenAI proxy
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
import tiktoken
import functions_framework

# Configure logging for Cloud Functions
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create separate logger for compression logging
compression_logger = logging.getLogger('compression')
compression_logger.setLevel(logging.INFO)

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
        
        # Log compression details
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

# Create FastAPI app
app = FastAPI(title="OpenAI Proxy", description="Transparent proxy to OpenAI API")

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
        
        # Update Content-Length if body was modified
        if body is not None:
            headers["content-length"] = str(len(body))
        
        # Log incoming request
        logger.info(f"Forwarding {request.method} {target_url}")
        
        response = await client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=request.query_params,
            content=body
        )
        
        # Handle streaming responses (like chat completions with stream=True)
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            async def stream_response():
                async for chunk in response.aiter_bytes():
                    yield chunk
            
            return StreamingResponse(
                stream_response(),
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="text/event-stream"
            )
        
        # Handle regular responses
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

# Google Cloud Functions entry point
import asyncio
from concurrent.futures import ThreadPoolExecutor

@functions_framework.http
def main(request):
    """Cloud Functions entry point"""
    # Convert Flask request to ASGI format
    import json
    from flask import request as flask_request
    
    # Get request details
    method = request.method
    path = request.path
    query_string = request.query_string.decode()
    headers = dict(request.headers)
    
    # Get body for POST/PUT/PATCH requests
    body = b""
    if method in ["POST", "PUT", "PATCH"]:
        body = request.get_data()
    
    # Create ASGI scope
    scope = {
        'type': 'http',
        'method': method,
        'path': path,
        'query_string': query_string.encode(),
        'headers': [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    
    # Handle the request with FastAPI
    async def run_asgi():
        # Create receive callable
        async def receive():
            return {
                'type': 'http.request',
                'body': body,
                'more_body': False,
            }
        
        # Create send callable and capture response
        response_data = {'status': 200, 'headers': [], 'body': b''}
        
        async def send(message):
            if message['type'] == 'http.response.start':
                response_data['status'] = message['status']
                response_data['headers'] = message.get('headers', [])
            elif message['type'] == 'http.response.body':
                response_data['body'] += message.get('body', b'')
        
        # Call FastAPI app
        await app(scope, receive, send)
        return response_data
    
    # Run the async function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        response_data = loop.run_until_complete(run_asgi())
    finally:
        loop.close()
    
    # Convert headers back to dict
    headers_dict = {}
    for header_tuple in response_data['headers']:
        key = header_tuple[0].decode() if isinstance(header_tuple[0], bytes) else header_tuple[0]
        value = header_tuple[1].decode() if isinstance(header_tuple[1], bytes) else header_tuple[1]
        headers_dict[key] = value
    
    # Return Flask response
    from flask import Response
    return Response(
        response=response_data['body'],
        status=response_data['status'],
        headers=headers_dict
    )

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting OpenAI proxy server on {host}:{port}")
    logger.info(f"Forwarding requests to {OPENAI_BASE_URL}")
    if COMPRESSION_RATIO > 1.0:
        logger.info(f"Compression enabled with ratio {COMPRESSION_RATIO} (removes ~{100*(1-1/COMPRESSION_RATIO):.1f}% of tokens)")
    else:
        logger.info("Compression disabled")
    
    uvicorn.run(app, host=host, port=port) 