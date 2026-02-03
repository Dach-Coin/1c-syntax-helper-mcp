#!/usr/bin/env python3
"""
Тест для проверки исправлений JSON-RPC в MCP сервере.
"""

import json
import requests

def test_mcp_protocol():
    """Тестирует исправления JSON-RPC протокола."""
    
    base_url = "http://localhost:8000/mcp"
    
    # Тест 1: Корректный initialize запрос
    print("Тест 1: Корректный initialize запрос")
    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "test-client",
                "version": "1.0.0"
            }
        }
    }
    
    try:
        response = requests.post(base_url, json=initialize_request, timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        print("✅ Тест 1 прошел")
    except Exception as e:
        print(f"❌ Ошибка теста 1: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Тест 2: Запрос без поля jsonrpc (должен вернуть ошибку)
    print("Тест 2: Запрос без поля jsonrpc")
    invalid_request = {
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    
    try:
        response = requests.post(base_url, json=invalid_request, timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        print("✅ Тест 2 прошел (ожидаемая ошибка)")
    except Exception as e:
        print(f"❌ Ошибка теста 2: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Тест 3: Запрос без обязательного поля id (должен вернуть ошибку)
    print("Тест 3: Запрос без обязательного поля id")
    no_id_request = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {}
    }
    
    try:
        response = requests.post(base_url, json=no_id_request, timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        print("✅ Тест 3 прошел (ожидаемая ошибка)")
    except Exception as e:
        print(f"❌ Ошибка теста 3: {e}")
    
    print("\n" + "="*50 + "\n")
    
    # Тест 4: Notification без id (должен пройти)
    print("Тест 4: Notification без id")
    notification_request = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {}
    }
    
    try:
        response = requests.post(base_url, json=notification_request, timeout=5)
        print(f"Статус: {response.status_code}")
        print(f"Ответ: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        print("✅ Тест 4 прошел")
    except Exception as e:
        print(f"❌ Ошибка теста 4: {e}")

if __name__ == "__main__":
    print("Запуск тестов MCP протокола...")
    print("Убедитесь, что сервер запущен на http://localhost:8000")
    test_mcp_protocol()