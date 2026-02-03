import urllib.request
import json

base_url = "http://localhost:9200"

# Список индексов
print("=== INDICES ===")
with urllib.request.urlopen(f"{base_url}/_cat/indices?format=json") as response:
    indices = json.loads(response.read().decode())
    for idx in indices:
        print(f"  {idx['index']}: {idx['docs.count']} docs, {idx['store.size']}")

# Статистика по типам документов
print("\n=== DOCUMENT TYPES ===")
query = {
    "size": 0,
    "aggs": {
        "types": {
            "terms": {"field": "type", "size": 20}
        }
    }
}
req = urllib.request.Request(
    f"{base_url}/help1c_docs/_search",
    data=json.dumps(query).encode(),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as response:
    result = json.loads(response.read().decode())
    for bucket in result["aggregations"]["types"]["buckets"]:
        print(f"  {bucket['key']}: {bucket['doc_count']}")

# Функции с параметрами
print("\n=== FUNCTIONS WITH PARAMETERS ===")
query = {
    "size": 5,
    "query": {
        "bool": {
            "must": [
                {"terms": {"type": ["object_function", "global_function", "object_procedure"]}}
            ]
        }
    }
}
req = urllib.request.Request(
    f"{base_url}/help1c_docs/_search",
    data=json.dumps(query).encode(),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as response:
    result = json.loads(response.read().decode())
    for hit in result["hits"]["hits"]:
        src = hit["_source"]
        params = src.get("parameters", [])
        if params:
            print(f"\n--- {src.get('object', 'global')}.{src['name']} ({src['type']}) ---")
            print(f"Syntax RU: {src.get('syntax_ru', '')}")
            print(f"Description: {src.get('description', '')[:150]}")
            print(f"Parameters ({len(params)}):")
            for p in params[:3]:
                print(f"  - {p.get('name')}: {p.get('type')} - {p.get('description', '')[:80]}")
            print(f"Return: {src.get('return_type')}")

# Поиск конкретного метода
print("\n\n=== SEARCH: 'Сообщить' ===")
query = {
    "size": 3,
    "query": {
        "multi_match": {
            "query": "Сообщить",
            "fields": ["name", "syntax_ru"]
        }
    }
}
req = urllib.request.Request(
    f"{base_url}/help1c_docs/_search",
    data=json.dumps(query).encode(),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as response:
    result = json.loads(response.read().decode())
    for hit in result["hits"]["hits"]:
        src = hit["_source"]
        print(f"\n--- {src.get('object', 'global')}.{src['name']} ---")
        print(f"Type: {src['type']}")
        print(f"Syntax RU: {src.get('syntax_ru', '')}")
        print(f"Description: {src.get('description', '')}")
        print(f"Parameters: {json.dumps(src.get('parameters', []), ensure_ascii=False)}")

# Глобальные функции
print("\n\n=== GLOBAL FUNCTIONS SAMPLE ===")
query = {
    "size": 5,
    "query": {"term": {"type": "global_function"}}
}
req = urllib.request.Request(
    f"{base_url}/help1c_docs/_search",
    data=json.dumps(query).encode(),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as response:
    result = json.loads(response.read().decode())
    for hit in result["hits"]["hits"]:
        src = hit["_source"]
        print(f"\n--- {src['name']} ---")
        print(f"Syntax RU: {src.get('syntax_ru', '')[:100]}")
        print(f"Return: {src.get('return_type')}")

# Документы с примерами
print("\n\n=== DOCS WITH EXAMPLES ===")
query = {
    "size": 2,
    "query": {
        "bool": {
            "must": [{"exists": {"field": "examples"}}],
            "must_not": [{"term": {"examples": ""}}]
        }
    },
    "_source": ["name", "object", "type", "examples"]
}
req = urllib.request.Request(
    f"{base_url}/help1c_docs/_search",
    data=json.dumps(query).encode(),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as response:
    result = json.loads(response.read().decode())
    print(f"Found: {result['hits']['total']['value']} docs with examples")
    for hit in result["hits"]["hits"]:
        src = hit["_source"]
        print(f"\n--- {src.get('object', '')}.{src['name']} ({src['type']}) ---")
        examples = src.get('examples', [])
        if isinstance(examples, list) and examples:
            print(f"Examples ({len(examples)}):")
            for ex in examples[:2]:
                print(f"  {ex[:200]}...")

