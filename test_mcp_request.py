#!/usr/bin/env python3
"""Test MCP endpoint request."""
import requests
import json

# JSON-RPC формат для MCP
payload = {
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
        "name": "find_1c_help",
        "arguments": {
            "query": "СтрДлина"
        }
    },
    "id": 1
}

try:
    response = requests.post(
        'http://localhost:8000/mcp',
        json=payload,
        timeout=30
    )
    print(f"Status: {response.status_code}")
    print(f"Response:\n{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
except requests.exceptions.ConnectionError as e:
    print(f"Connection Error: сервер не запущен на localhost:8000")
    print(f"Details: {e}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

