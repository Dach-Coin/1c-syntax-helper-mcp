# Тесты проекта

Этот каталог содержит все тесты для MCP сервера синтаксис-помощника 1С.

## Структура

- `conftest.py` - конфигурация pytest, mock фикстуры
- `pytest.ini` - настройки pytest и маркеры (в корне проекта)
- `fixtures/` - тестовые данные и фикстуры

### Unit тесты (быстрые, с mock)
- `test_parsing_unit.py` - тесты парсера с mock данными
- `test_indexing_unit.py` - тесты индексатора с mock
- `test_retry_mechanisms.py` - тесты retry логики
- `test_background_indexing.py` - тесты фоновой индексации
- `test_reindex_config.py` - тесты конфигурации

### Integration тесты (медленные, с реальными данными)
- `test_parsing.py` - полный парсинг .hbk файла
- `test_indexing.py` - реальная индексация в Elasticsearch
- `test_elasticsearch_connection.py` - подключение к ES
- `test_search.py` - поиск в реальном индексе

## Запуск тестов

### 🚀 Быстрые unit тесты (для разработки)
```bash
# Только unit тесты (< 5 сек)
pytest -m unit

# Unit тесты с подробным выводом
pytest -m unit -v

# Конкретная категория unit тестов
pytest -m "unit and parser"
pytest -m "unit and indexer"
```

### 🔬 Integration тесты (для предрелизной проверки)
```bash
# Только integration тесты (медленно!)
pytest -m integration

# Integration тесты конкретного модуля
pytest -m "integration and elasticsearch"
pytest -m "integration and search"
```

### 📊 Все тесты
```bash
# Все тесты (unit + integration)
pytest tests/

# Все тесты с покрытием
pytest tests/ --cov=src
```

### 🎯 Запуск конкретного теста
```bash
# Unit тест парсера
pytest tests/test_parsing_unit.py -v

# Integration тест индексации
pytest tests/test_indexing.py -v

# Конкретная тестовая функция
pytest tests/test_parsing_unit.py::test_parsed_hbk_structure -v
```

### ⚡ Полезные комбинации
```bash
# Пропустить медленные тесты
pytest -m "not slow"

# Только тесты парсера (unit + integration)
pytest -m parser

# Только тесты без ES
pytest -m "not elasticsearch"

# Verbose вывод + остановка на первой ошибке
pytest -v -x
```

## Соглашения

1. **Именование файлов:** 
   - Unit тесты: `test_<модуль>_unit.py`
   - Integration тесты: `test_<модуль>.py`

2. **Именование функций:** `test_<функциональность>()`

3. **Маркеры:**
   - Обязательно помечать unit тесты `@pytest.mark.unit`
   - Обязательно помечать integration тесты `@pytest.mark.integration`
   - Помечать медленные тесты `@pytest.mark.slow`
   - Указывать зависимости: `@pytest.mark.elasticsearch`, etc.

4. **Асинхронные тесты:** используйте `@pytest.mark.asyncio`

5. **Фикстуры:** 
   - Mock фикстуры в `conftest.py`
   - Реальные данные через параметры или setup

## Рекомендации по workflow

### Во время разработки
```bash
# Быстрая проверка после изменений
pytest -m unit -v

# Проверка конкретного модуля
pytest -m "unit and parser" -v
```

### Перед коммитом
```bash
# Все unit тесты + быстрые integration
pytest -m "unit or (integration and not slow)" -v
```

### Перед релизом
```bash
# Полный набор тестов
pytest tests/ -v

# С покрытием кода
pytest tests/ --cov=src --cov-report=html
```

### В CI/CD
```bash
# Unit тесты (быстро, всегда)
pytest -m unit --tb=short

# Integration тесты (на staging/pre-release)
pytest -m integration --tb=short
```

## Категории тестов

### Unit тесты
**Маркер:** `@pytest.mark.unit`  
**Характеристики:**
- ⚡ Быстрые (< 5 секунд)
- 🎯 Изолированные с mock данными
- 🔧 Без внешних зависимостей (ES, файлы)
- 💻 Для разработки и CI/CD

**Примеры:**
- `test_parsing_unit.py` - тесты парсера с mock данными
- `test_indexing_unit.py` - тесты индексатора с mock
- `test_retry_mechanisms.py` - тесты retry логики

### Integration тесты  
**Маркер:** `@pytest.mark.integration`  
**Характеристики:**
- 🐌 Медленные (до 20 минут)
- 🔗 С реальными компонентами (ES, файлы)
- 📦 Полный парсинг .hbk файлов
- 🚀 Для предрелизной проверки

**Примеры:**
- `test_parsing.py` - полный парсинг .hbk файла
- `test_indexing.py` - реальная индексация в ES
- `test_search.py` - поиск в реальном индексе

### Дополнительные маркеры

- `@pytest.mark.slow` - очень медленные тесты (> 10 сек)
- `@pytest.mark.elasticsearch` - требуют ES
- `@pytest.mark.parser` - тесты парсера
- `@pytest.mark.indexer` - тесты индексатора
- `@pytest.mark.search` - тесты поиска
- `@pytest.mark.background` - тесты фоновых задач
- `@pytest.mark.retry` - тесты retry механизмов

## Примеры

### Unit тест с mock данными
```python
import pytest

@pytest.mark.unit
@pytest.mark.parser
def test_parsing_logic(mock_parsed_hbk):
    """Быстрый тест логики парсера."""
    assert len(mock_parsed_hbk.documentation) > 0
    assert mock_parsed_hbk.file_info is not None
```

### Integration тест с реальными данными
```python
import pytest

@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.elasticsearch
@pytest.mark.asyncio
async def test_full_indexing():
    """Полная индексация с реальным .hbk файлом."""
    parser = HBKParser()
    parsed = parser.parse_file("data/hbk/shcntx_ru.hbk")
    
    indexer = ElasticsearchIndexer(es_client)
    result = await indexer.reindex_all(parsed)
    
    assert result is True
```

### Асинхронный unit тест
```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.unit
@pytest.mark.asyncio
async def test_async_operation(mock_elasticsearch_indexer):
    """Тест асинхронной операции с mock."""
    result = await mock_elasticsearch_indexer.reindex_all(mock_data)
    assert result is True
```
