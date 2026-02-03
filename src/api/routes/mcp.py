"""MCP protocol endpoints."""

import json
import asyncio
import time
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from src.core.logging import get_logger
from src.core.elasticsearch import ElasticsearchClient
from src.api.dependencies import get_elasticsearch_client
from src.models.mcp_models import (
    MCPRequest, MCPResponse, MCPToolsResponse, MCPTool, MCPToolParameter, MCPToolType,
    Find1CHelpRequest, GetSyntaxInfoRequest, GetQuickReferenceRequest,
    SearchByContextRequest, ListObjectMembersRequest
)
from src.handlers.mcp_handlers import (
    handle_find_1c_help, handle_get_syntax_info, handle_get_quick_reference,
    handle_search_by_context, handle_list_object_members
)

router = APIRouter(prefix="/mcp", tags=["mcp"])
logger = get_logger(__name__)


@router.get("/tools", response_model=MCPToolsResponse)
async def get_mcp_tools():
    """Возвращает список доступных MCP инструментов."""
    tools = [
        MCPTool(
            name=MCPToolType.FIND_1C_HELP,
            description="Универсальный поиск справки по любому элементу 1С",
            parameters=[
                MCPToolParameter(
                    name="query",
                    type="string",
                    description="Поисковый запрос (имя элемента, описание, ключевые слова)",
                    required=True
                ),
                MCPToolParameter(
                    name="limit",
                    type="number",
                    description="Максимальное количество результатов (по умолчанию: 10)",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.GET_SYNTAX_INFO,
            description="Получить полную техническую информацию об элементе с синтаксисом и параметрами",
            parameters=[
                MCPToolParameter(
                    name="element_name",
                    type="string",
                    description="Имя элемента (функции, метода, свойства)",
                    required=True
                ),
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="Имя объекта (для методов объектов)",
                    required=False
                ),
                MCPToolParameter(
                    name="include_examples",
                    type="boolean",
                    description="Включить примеры использования",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.GET_QUICK_REFERENCE,
            description="Получить краткую справку об элементе (только синтаксис и описание)",
            parameters=[
                MCPToolParameter(
                    name="element_name",
                    type="string",
                    description="Имя элемента",
                    required=True
                ),
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="Имя объекта (необязательно)",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.SEARCH_BY_CONTEXT,
            description="Поиск элементов с фильтром по контексту (глобальные функции или методы объектов)",
            parameters=[
                MCPToolParameter(
                    name="query",
                    type="string",
                    description="Поисковый запрос",
                    required=True
                ),
                MCPToolParameter(
                    name="context",
                    type="string",
                    description="Контекст поиска: global, object, all",
                    required=True
                ),
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="Фильтр по конкретному объекту (для context=object)",
                    required=False
                ),
                MCPToolParameter(
                    name="limit",
                    type="number",
                    description="Максимальное количество результатов",
                    required=False
                )
            ]
        ),
        MCPTool(
            name=MCPToolType.LIST_OBJECT_MEMBERS,
            description="Получить список всех элементов объекта (методы, свойства, события)",
            parameters=[
                MCPToolParameter(
                    name="object_name",
                    type="string",
                    description="Имя объекта 1С",
                    required=True
                ),
                MCPToolParameter(
                    name="member_type",
                    type="string",
                    description="Тип элементов: all, methods, properties, events",
                    required=False
                ),
                MCPToolParameter(
                    name="limit",
                    type="number",
                    description="Максимальное количество результатов",
                    required=False
                )
            ]
        )
    ]
    
    return MCPToolsResponse(tools=tools)


@router.get("")
async def mcp_sse_endpoint():
    """MCP Server-Sent Events endpoint для потокового соединения."""
    async def event_stream():
        # Отправляем JSON-RPC endpoint message
        endpoint_message = {
            "jsonrpc": "2.0",
            "method": "endpoint",
            "params": {
                "uri": "http://localhost:8000/mcp",
                "transport": {
                    "type": "http",
                    "requestType": "post"
                }
            }
        }
        yield f"data: {json.dumps(endpoint_message)}\n\n"
        
        # Поддерживаем соединение живым
        while True:
            await asyncio.sleep(30)
            yield f"data: {json.dumps({'type': 'ping', 'timestamp': int(time.time())})}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("")
async def mcp_jsonrpc_endpoint(
    request: Request,
    es_client: ElasticsearchClient = Depends(get_elasticsearch_client)
):
    """MCP JSON-RPC endpoint для обработки MCP протокола."""
    try:
        body = await request.body()
        data = json.loads(body.decode('utf-8'))
        
        # Логируем входящий запрос для диагностики
        logger.debug(f"MCP JSON-RPC запрос получен: {data}")
        
        # Проверяем JSON-RPC формат
        jsonrpc_version = data.get("jsonrpc")
        if jsonrpc_version is None or jsonrpc_version != "2.0":
            logger.warning(f"Некорректная версия JSON-RPC: {jsonrpc_version}")
            return JSONResponse(
                status_code=400,
                content={"error": {"code": -32600, "message": "Invalid Request"}}
            )
        
        method = data.get("method")
        params = data.get("params", {})
        request_id = data.get("id")
        
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
        
        # Обрабатываем initialize запрос
        if method == "initialize":
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {
                        "tools": {},
                        "resources": {},
                        "prompts": {},
                        "roots": {"listChanged": False},
                        "sampling": {}
                    },
                    "serverInfo": {
                        "name": "1c-syntax-helper-mcp",
                        "version": "1.0.0"
                    }
                }
            })
        
        # Обрабатываем tools/list запрос
        elif method == "tools/list":
            tools_response = await get_mcp_tools()
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    param.name: {
                                        "type": param.type,
                                        "description": param.description
                                    }
                                    for param in tool.parameters
                                },
                                "required": [param.name for param in tool.parameters if param.required]
                            }
                        }
                        for tool in tools_response.tools
                    ]
                }
            })
        
        # Обрабатываем prompts/list запрос
        elif method == "prompts/list":
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "prompts": []
                }
            })
        
        # Обрабатываем resources/list запрос
        elif method == "resources/list":
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "resources": []
                }
            })
        
        # Обрабатываем resources/templates/list запрос
        elif method == "resources/templates/list":
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "resources": []
                }
            })
        
        # Обрабатываем notifications/initialized (без ответа)
        elif method == "notifications/initialized":
            # Notifications не должны возвращать ответ с id
            return JSONResponse(content={})
        
        # Обрабатываем tools/call запрос
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            # Преобразуем в наш формат MCPRequest
            mcp_request = MCPRequest(tool=tool_name, arguments=arguments)
            
            # Вызываем наш существующий обработчик
            result = await mcp_endpoint_handler(mcp_request, es_client)
            
            return JSONResponse(content={
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": result.content if hasattr(result, 'content') else result,
                    "isError": False
                }
            })
        
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
            )
            
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"error": {"code": -32700, "message": "Parse error"}}
        )
    except Exception as e:
        logger.error(f"Ошибка в MCP JSON-RPC endpoint: {e}")
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": request_id if 'request_id' in locals() and request_id is not None else None,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
            }
        )


async def mcp_endpoint_handler(request: MCPRequest, es_client: ElasticsearchClient):
    """Внутренний обработчик MCP запросов."""
    logger.info(f"Получен MCP запрос: {request.tool}")
    
    try:
        # Проверяем подключение к Elasticsearch
        if not await es_client.is_connected():
            raise HTTPException(
                status_code=503, 
                detail="Elasticsearch недоступен"
            )
        
        # Маршрутизируем запрос к новым обработчикам
        if request.tool == MCPToolType.FIND_1C_HELP:
            return await handle_find_1c_help(Find1CHelpRequest(**request.arguments), es_client)
        elif request.tool == MCPToolType.GET_SYNTAX_INFO:
            return await handle_get_syntax_info(GetSyntaxInfoRequest(**request.arguments), es_client)
        elif request.tool == MCPToolType.GET_QUICK_REFERENCE:
            return await handle_get_quick_reference(GetQuickReferenceRequest(**request.arguments), es_client)
        elif request.tool == MCPToolType.SEARCH_BY_CONTEXT:
            return await handle_search_by_context(SearchByContextRequest(**request.arguments), es_client)
        elif request.tool == MCPToolType.LIST_OBJECT_MEMBERS:
            return await handle_list_object_members(ListObjectMembersRequest(**request.arguments), es_client)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Неизвестный инструмент: {request.tool}"
            )
            
    except Exception as e:
        logger.error(f"Ошибка обработки MCP запроса: {e}")
        return MCPResponse(content=[], error=str(e))
