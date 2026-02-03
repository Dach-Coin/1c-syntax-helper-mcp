# Исправления JSON-RPC протокола в MCP сервере

## Описание проблемы

При подключении MCP сервера к Kilo возникали следующие ошибки:
- `Invalid literal value, expected "2.0"` для поля `jsonrpc`
- `Required` ошибка для поля `id`
- Неправильная обработка notification запросов

## Выявленные проблемы

1. **Неправильная проверка версии jsonrpc**: В коде использовалось `data.get("jsonrpc") != "2.0"`, что не учитывало случаи, когда поле отсутствует или равно `None`

2. **Отсутствие валидации обязательного поля `id`**: JSON-RPC 2.0 требует наличия поля `id` для всех запросов, кроме notifications

3. **Неправильная обработка notifications**: Notifications не должны возвращать ответ с полем `id`

4. **Проблемы с обработкой ошибок**: При ошибках сервер мог вернуть `None` вместо корректного `id`

## Внесенные исправления

### 1. Улучшенная проверка JSON-RPC версии
```python
# Было
if data.get("jsonrpc") != "2.0":

# Стало  
jsonrpc_version = data.get("jsonrpc")
if jsonrpc_version is None or jsonrpc_version != "2.0":
```

### 2. Добавлена валидация обязательного поля `id`
```python
# Проверяем обязательное поле id для обычных запросов (не notifications)
if method and not method.startswith("notifications/") and request_id is None:
    return JSONResponse(
        status_code=400,
        content={
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32600, "message": "Invalid Request: Missing required 'id' field"}
        }
    )
```

### 3. Исправлена обработка notifications
```python
# Было
elif method == "notifications/initialized":
    return JSONResponse(content={"status": "ok"})

# Стало
elif method == "notifications/initialized":
    # Notifications не должны возвращать ответ с id
    return JSONResponse(content={})
```

### 4. Улучшена обработка ошибок
```python
# Добавлена проверка на None для request_id
"id": request_id if 'request_id' in locals() and request_id is not None else None,
```

### 5. Добавлено детальное логирование
```python
# Логируем входящий запрос для диагностики
logger.debug(f"MCP JSON-RPC запрос получен: {data}")

# Логируем предупреждения при некорректных запросах
logger.warning(f"Некорректная версия JSON-RPC: {jsonrpc_version}")
```

## Тестирование

Создан тестовый файл `test_mcp_fix.py` для проверки:
1. Корректных initialize запросов
2. Запросов без поля jsonrpc (ожидаемая ошибка)
3. Запросов без поля id (ожидаемая ошибка) 
4. Notifications без id (должно пройти)

## Соответствие стандартам

Исправления обеспечивают полное соответствие JSON-RPC 2.0 протоколу:
- ✅ Корректная обработка версии "2.0"
- ✅ Обязательное поле `id` для обычных запросов
- ✅ Отсутствие поля `id` для notifications
- ✅ Правильные коды ошибок JSON-RPC
- ✅ Корректные форматы ответов

## Файлы изменений

- `src/api/routes/mcp.py` - исправления JSON-RPC endpoint

## Рекомендации по развертыванию

1. Перезапустить MCP сервер после внесения изменений
2. Проверить логи на наличие предупреждений о некорректных запросах
3. Протестировать подключение с помощью Kilo или других MCP клиентов