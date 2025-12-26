"""Retry механизмы для устойчивости к временным сбоям."""

import logging
from functools import wraps
from typing import Callable
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log
)
from elasticsearch.exceptions import ConnectionError, TransportError

from src.core.logging import get_logger
from src.core.config import settings

logger = get_logger(__name__)


def retry_on_connection_error(func: Callable) -> Callable:
    """
    Декоратор для retry при ошибках подключения к Elasticsearch.
    
    Стратегия:
    - Максимум попыток из настроек (default: 5)
    - Exponential backoff с параметрами из конфига
    - Retry только при ConnectionError
    - Логирование каждой попытки
    
    Args:
        func: Async функция для декорирования
        
    Returns:
        Декорированная функция с retry механизмом
    """
    es_config = settings.elasticsearch
    
    @retry(
        stop=stop_after_attempt(es_config.max_retries),
        wait=wait_exponential(
            multiplier=es_config.retry_multiplier,
            min=es_config.retry_min_wait,
            max=es_config.retry_max_wait
        ),
        retry=retry_if_exception_type(ConnectionError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True
    )
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    
    return wrapper


def retry_on_transient_error(func: Callable) -> Callable:
    """
    Декоратор для retry при временных ошибках Elasticsearch.
    
    Стратегия:
    - Максимум 3 попытки (меньше, т.к. это обычно не критично)
    - Exponential backoff: 2s, 4s, 8s
    - Retry при ConnectionError и TransportError (503, 504, timeout)
    - Логирование каждой попытки
    
    Args:
        func: Async функция для декорирования
        
    Returns:
        Декорированная функция с retry механизмом
    """
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(
            multiplier=1,
            min=2,
            max=10
        ),
        retry=retry_if_exception_type((ConnectionError, TransportError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        after=after_log(logger, logging.INFO),
        reraise=True
    )
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await func(*args, **kwargs)
    
    return wrapper


def create_retry_decorator(
    max_attempts: int = 3,
    min_wait: int = 2,
    max_wait: int = 30,
    multiplier: int = 1
) -> Callable:
    """
    Создаёт кастомный retry декоратор с настраиваемыми параметрами.
    
    Args:
        max_attempts: Максимальное количество попыток
        min_wait: Минимальная пауза между попытками (секунды)
        max_wait: Максимальная пауза между попытками (секунды)
        multiplier: Множитель для exponential backoff
        
    Returns:
        Retry декоратор с указанными параметрами
    """
    def decorator(func: Callable) -> Callable:
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(
                multiplier=multiplier,
                min=min_wait,
                max=max_wait
            ),
            retry=retry_if_exception_type((ConnectionError, TransportError)),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            after=after_log(logger, logging.INFO),
            reraise=True
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator
