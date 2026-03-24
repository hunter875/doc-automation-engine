#!/usr/bin/env python3
"""Test script to check Ollama connectivity from container"""

import requests
import sys

body = {
    'model': 'qwen3:8b',
    'messages': [{'role': 'user', 'content': 'Hello, respond with one word'}],
    'stream': False
}

try:
    print("Testing Ollama API from container...")
    print("Sending request to http://host.docker.internal:11434/v1/chat/completions")
    print("Timeout: 60 seconds")
    
    resp = requests.post(
        'http://host.docker.internal:11434/v1/chat/completions', 
        json=body, 
        timeout=60
    )
    
    print(f'\nStatus Code: {resp.status_code}')
    
    if resp.status_code == 200:
        result = resp.json()
        print(f'✓ SUCCESS!')
        print(f'Model: {result.get("model", "?")}')
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '').strip()
        print(f'Response: {content[:200]}')
        sys.exit(0)
    else:
        print(f'✗ ERROR {resp.status_code}')
        print(f'Response: {resp.text[:500]}')
        sys.exit(1)
        
except requests.exceptions.Timeout as e:
    print(f'✗ TIMEOUT ERROR: {e}')
    print('Ollama server is not responding within 60 seconds')
    print('The model might be too slow or not fully loaded')
    sys.exit(2)
    
except Exception as e:
    print(f'✗ CONNECTION ERROR: {e}')
    sys.exit(3)
