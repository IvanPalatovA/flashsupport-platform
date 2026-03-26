# FlashSupport RAG Service (MVP)

Retrieval-only сервис семантического поиска для FlashSupport.

## Что делает

- принимает текстовый запрос через HTTP API;
- выполняет top-k поиск по `chunks.embedding` (pgvector);
- возвращает результаты с метаданными документа;
- не выполняет ingestion, parsing, chunking, indexing, upload.

## API

- `GET /health` -> `{ "status": "ok" }`
- `POST /search`

Request:

```json
{
  "query": "как сбросить пароль",
  "top_k": 3
}
```

Response:

```json
{
  "query": "как сбросить пароль",
  "top_k": 3,
  "results": [
    {
      "chunk_id": 1,
      "document_id": 1,
      "document_title": "Password reset guide",
      "chunk_index": 0,
      "score": 0.91,
      "text": "..."
    }
  ]
}
```

## Запуск через Docker Compose

Из корня репозитория:

```bash
docker compose --env-file .env.dev -f docker-compose.yml up -d --build
```

Для prod:

```bash
docker compose --env-file .env.prod -f docker-compose.yml up -d --build
```

Проверка сервиса:

```bash
curl http://localhost:8080/health
```

Ожидается:

```json
{"status":"ok"}
```

Важно: достаточно выбрать только `--env-file` (`.env.dev` или `.env.prod`). Из него Compose берёт `RAG_ENGINE_ENV`, подключает `services/RAG Engine/.env.<mode>` и прокидывает `RAG_ENGINE_ENV` в контейнер.

Swagger: 

- `http://localhost:8080/docs`

## Важно по данным

Сервис только читает данные из PostgreSQL/pgvector. Наполнение таблиц и подготовка embeddings делает внешняя утилита.

Минимально ожидаемая схема:

- `documents(id, title, source, created_at)`
- `chunks(id, document_id, chunk_index, text, embedding, created_at)`

где `embedding` имеет тип `vector(VECTOR_DIMENSION)`.

## Локальный запуск (без Docker)

```bash
cd "services/RAG Engine"
python -m venv .venv
source .venv/bin/activate
pip install -e .[test]
cp .env.example .env
uvicorn main:app --app-dir src --host 0.0.0.0 --port 8080
```

## Тесты

```bash
docker run --rm -v "$PWD/services/RAG Engine:/work" -w /work python:3.11.8-slim-bookworm sh -lc "python -m pip install --no-cache-dir -e '.[test]' && pytest -q"
```
