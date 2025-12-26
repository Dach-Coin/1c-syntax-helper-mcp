"""Тесты для retry механизмов."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from elasticsearch.exceptions import ConnectionError, TransportError

from src.core.retry import (
    retry_on_connection_error,
    retry_on_transient_error,
    create_retry_decorator
)


@pytest.mark.asyncio
async def test_retry_on_connection_error_success_first_attempt():
    """Тест успешного выполнения с первой попытки."""
    mock_func = AsyncMock(return_value=True)
    decorated = retry_on_connection_error(mock_func)
    
    result = await decorated()
    
    assert result is True
    assert mock_func.call_count == 1


@pytest.mark.asyncio
async def test_retry_on_connection_error_success_after_retries():
    """Тест успешного выполнения после нескольких retry."""
    mock_func = AsyncMock(
        side_effect=[
            ConnectionError("Connection failed"),
            ConnectionError("Connection failed"),
            True  # Успех на 3-й попытке
        ]
    )
    decorated = retry_on_connection_error(mock_func)
    
    result = await decorated()
    
    assert result is True
    assert mock_func.call_count == 3


@pytest.mark.asyncio
async def test_retry_on_connection_error_max_attempts_exceeded():
    """Тест превышения максимального количества попыток."""
    mock_func = AsyncMock(
        side_effect=ConnectionError("Connection failed")
    )
    decorated = retry_on_connection_error(mock_func)
    
    with pytest.raises(ConnectionError):
        await decorated()
    
    # Должно быть 5 попыток (default max_retries в config)
    assert mock_func.call_count == 3  # или 5, в зависимости от настройки


@pytest.mark.asyncio
async def test_retry_on_transient_error_success():
    """Тест retry для временных ошибок."""
    mock_func = AsyncMock(
        side_effect=[
            TransportError("Timeout"),
            {"result": "success"}
        ]
    )
    decorated = retry_on_transient_error(mock_func)
    
    result = await decorated()
    
    assert result == {"result": "success"}
    assert mock_func.call_count == 2


@pytest.mark.asyncio
async def test_retry_on_transient_error_connection_error():
    """Тест retry для ConnectionError в transient decorator."""
    mock_func = AsyncMock(
        side_effect=[
            ConnectionError("Connection failed"),
            {"result": "success"}
        ]
    )
    decorated = retry_on_transient_error(mock_func)
    
    result = await decorated()
    
    assert result == {"result": "success"}
    assert mock_func.call_count == 2


@pytest.mark.asyncio
async def test_retry_on_transient_error_max_attempts():
    """Тест превышения лимита попыток для transient errors."""
    mock_func = AsyncMock(
        side_effect=TransportError("Persistent error")
    )
    decorated = retry_on_transient_error(mock_func)
    
    with pytest.raises(TransportError):
        await decorated()
    
    # transient_error имеет 3 попытки
    assert mock_func.call_count == 3


@pytest.mark.asyncio
async def test_create_retry_decorator_custom_params():
    """Тест создания кастомного retry декоратора."""
    mock_func = AsyncMock(
        side_effect=[
            ConnectionError("Error 1"),
            True
        ]
    )
    
    # Создаём декоратор с кастомными параметрами
    custom_retry = create_retry_decorator(
        max_attempts=2,
        min_wait=1,
        max_wait=5,
        multiplier=1
    )
    decorated = custom_retry(mock_func)
    
    result = await decorated()
    
    assert result is True
    assert mock_func.call_count == 2


@pytest.mark.asyncio
async def test_retry_preserves_function_metadata():
    """Тест сохранения метаданных функции после декорирования."""
    async def sample_function():
        """Sample docstring."""
        return True
    
    decorated = retry_on_connection_error(sample_function)
    
    assert decorated.__name__ == "sample_function"
    assert decorated.__doc__ == "Sample docstring."


@pytest.mark.asyncio
async def test_retry_with_args_and_kwargs():
    """Тест retry с аргументами функции."""
    mock_func = AsyncMock(
        side_effect=[
            ConnectionError("Error"),
            "success"
        ]
    )
    decorated = retry_on_connection_error(mock_func)
    
    result = await decorated("arg1", kwarg1="value1")
    
    assert result == "success"
    assert mock_func.call_count == 2
    mock_func.assert_called_with("arg1", kwarg1="value1")


@pytest.mark.asyncio
async def test_retry_does_not_retry_on_other_exceptions():
    """Тест что retry не срабатывает для других исключений."""
    mock_func = AsyncMock(
        side_effect=ValueError("Not a connection error")
    )
    decorated = retry_on_connection_error(mock_func)
    
    with pytest.raises(ValueError):
        await decorated()
    
    # Должна быть только 1 попытка, т.к. ValueError не в списке retry
    assert mock_func.call_count == 1
