#!/usr/bin/env python3
"""
Simple Google Cloud Functions proxy to OpenAI API with compression
"""

import os
import json
import logging
import random
import requests
from typing import Any, Dict, Optional
from datetime import datetime
import tiktoken
import functions_framework

# Configure logging
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
_TOKENS_TO_KEEP_RATIO_ENV = os.getenv("TOKENS_TO_KEEP_RATIO", None)
TOKENS_TO_KEEP_RATIO = None if _TOKENS_TO_KEEP_RATIO_ENV in (None, "") else float(_TOKENS_TO_KEEP_RATIO_ENV)

def compress_text(text: str, compression_ratio: float, tokens_to_keep_ratio: Optional[float] = None) -> str:
    """
    Simple token-based compression algorithm.
    Removes N random tokens where:
      - If tokens_to_keep_ratio is provided and < 1.0: N = token_count * (1 - tokens_to_keep_ratio)
      - Else if compression_ratio > 1.0: N = token_count * (1 - 1/compression_ratio)
    """
    if tokens_to_keep_ratio is not None:
        if tokens_to_keep_ratio >= 1.0:
            return text
    elif compression_ratio <= 1.0:
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
        if tokens_to_keep_ratio is not None and tokens_to_keep_ratio < 1.0:
            tokens_to_remove = int(token_count * (1 - tokens_to_keep_ratio))
        else:
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
        compression_logger.info(f"COMPRESSION APPLIED - Ratio: {compression_ratio}, TokensToKeepRatio: {tokens_to_keep_ratio}")
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

def compress_chat_messages(messages: list, compression_ratio: float, tokens_to_keep_ratio: Optional[float] = None) -> list:
    """
    Apply compression to chat messages, focusing on user messages
    """
    if tokens_to_keep_ratio is not None:
        if tokens_to_keep_ratio >= 1.0:
            return messages
    elif compression_ratio <= 1.0:
        return messages
    
    compressed_messages = []
    user_message_count = 0
    
    for i, message in enumerate(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content", "")
            if isinstance(content, str):
                user_message_count += 1
                compression_logger.info(f"COMPRESSING USER MESSAGE #{user_message_count} (position {i})")
                compressed_content = compress_text(content, compression_ratio, tokens_to_keep_ratio)
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

@functions_framework.http
def main(request):
    """Google Cloud Functions entry point"""
    try:
        # Handle health check
        if request.path == '/health':
            return {"status": "healthy", "proxy_target": OPENAI_BASE_URL}
        
        # Get the path, removing leading slash if it exists
        path = request.path
        if path.startswith('/'):
            path = path[1:]
        
        # Build target URL
        target_url = f"{OPENAI_BASE_URL}/{path}"
        
        # Get request body
        body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            body = request.get_data()
            
            # Apply compression for chat completions
            should_compress = False
            if TOKENS_TO_KEEP_RATIO is not None:
                should_compress = TOKENS_TO_KEEP_RATIO < 1.0
            else:
                should_compress = COMPRESSION_RATIO > 1.0
            if body and path.endswith("chat/completions") and should_compress:
                try:
                    body_str = body.decode('utf-8')
                    body_data = json.loads(body_str)
                    if "messages" in body_data and isinstance(body_data["messages"], list):
                        compression_logger.info(f"NEW CHAT COMPLETION REQUEST - Timestamp: {datetime.now().isoformat()}")
                        compression_logger.info(f"Target URL: {target_url}")
                        compression_logger.info(f"Compression ratio: {COMPRESSION_RATIO}")
                        compression_logger.info(f"Tokens to keep ratio: {TOKENS_TO_KEEP_RATIO}")
                        compression_logger.info("")
                        
                        body_data["messages"] = compress_chat_messages(body_data["messages"], COMPRESSION_RATIO, TOKENS_TO_KEEP_RATIO)
                        new_body_str = json.dumps(body_data, ensure_ascii=False)
                        body = new_body_str.encode('utf-8')
                        if TOKENS_TO_KEEP_RATIO is not None:
                            logger.info(f"Applied tokens_to_keep_ratio {TOKENS_TO_KEEP_RATIO} to chat completion request")
                        else:
                            logger.info(f"Applied compression ratio {COMPRESSION_RATIO} to chat completion request")
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON for compression: {e}")
                except UnicodeDecodeError as e:
                    logger.warning(f"Failed to decode body for compression: {e}")
                except Exception as e:
                    logger.warning(f"Failed to apply compression: {e}")
        
        # Prepare headers
        headers = dict(request.headers)
        
        # Remove problematic headers
        headers.pop("host", None)
        headers.pop("content-length", None)
        
        # Log request
        logger.info(f"Forwarding {request.method} {target_url}")
        
        # Make the request to OpenAI
        response = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=request.args,
            data=body,
            stream=True,
            timeout=300
        )
        
        # Handle streaming responses
        if response.headers.get("content-type", "").startswith("text/event-stream"):
            def generate():
                try:
                    for chunk in response.iter_content(chunk_size=1024):
                        if chunk:
                            yield chunk
                except Exception as e:
                    logger.error(f"Streaming error: {e}")
                    yield f"data: {json.dumps({'error': 'Streaming error'})}\n\n".encode()
            
            from flask import Response
            return Response(
                generate(),
                status=response.status_code,
                headers=dict(response.headers),
                mimetype="text/event-stream"
            )
        
        # Handle regular responses
        from flask import Response
        return Response(
            response.content,
            status=response.status_code,
            headers=dict(response.headers)
        )
        
    except requests.RequestException as e:
        logger.error(f"Request error: {e}")
        from flask import Response
        return Response(
            json.dumps({"error": "Bad Gateway - Failed to connect to OpenAI API"}),
            status=502,
            headers={"Content-Type": "application/json"}
        )
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        from flask import Response
        return Response(
            json.dumps({"error": "Internal Server Error"}),
            status=500,
            headers={"Content-Type": "application/json"}
        )

if __name__ == "__main__":
    # For local testing
    from flask import Flask
    app = Flask(__name__)
    
    @app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
    @app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'])
    def proxy(path):
        from flask import request
        return main(request)
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting OpenAI proxy server on {host}:{port}")
    logger.info(f"Forwarding requests to {OPENAI_BASE_URL}")
    if TOKENS_TO_KEEP_RATIO is not None and TOKENS_TO_KEEP_RATIO < 1.0:
        logger.info(f"Compression enabled with tokens_to_keep_ratio {TOKENS_TO_KEEP_RATIO} (removes ~{100*(1-TOKENS_TO_KEEP_RATIO):.1f}% of tokens)")
    elif COMPRESSION_RATIO > 1.0:
        logger.info(f"Compression enabled with ratio {COMPRESSION_RATIO} (removes ~{100*(1-1/COMPRESSION_RATIO):.1f}% of tokens)")
    else:
        logger.info("Compression disabled")
    
    app.run(host=host, port=port, debug=False) 