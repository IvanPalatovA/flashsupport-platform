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
docker compose --env-file .env.public.dev -f docker-compose.yml up -d --build
```

Для prod:

```bash
docker compose --env-file .env.public.prod -f docker-compose.yml up -d --build
```

Проверка сервиса:

```bash
curl http://localhost:8080/health
```

Ожидается:

```json
{"status":"ok"}
```

Важно: достаточно выбрать только `--env-file` (`.env.public.dev` или `.env.public.prod`). Из него Compose берёт `RAG_ENGINE_ENV`, подключает `services/RAG Engine/.env.<mode>` и прокидывает `RAG_ENGINE_ENV` в контейнер.

Для `dev` Compose также поднимает локальный PostgreSQL с `pgvector` (`service: postgres`), который использует `rag-service`.
При необходимости параметры БД можно переопределить через переменные `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` в момент запуска Compose.

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

## MacBook MPS

Apple MPS/Metal не пробрасывается в Linux-контейнер Docker Desktop. Если RAG Engine запущен в Docker на MacBook, `torch.backends.mps.is_available()` будет `False`, и embedding-модель будет работать на CPU.

Для MPS запускайте RAG Engine нативно на macOS, а остальные сервисы оставляйте в Docker:

```bash
docker compose --env-file .env.public.dev -f docker-compose.yml -f docker-compose.macos-mps.yml up -d --build
./scripts/run-rag-macos-mps.sh
```

Скрипт запускает RAG Engine на `http://localhost:18080` с `EMBEDDING_DEVICE=mps`. Override-файл `docker-compose.macos-mps.yml` направляет `web-service` и `chat-orchestrator` на `http://host.docker.internal:18080`.

## Тесты

```bash
docker run --rm -v "$PWD/services/RAG Engine:/work" -w /work python:3.11.8-slim-bookworm sh -lc "python -m pip install --no-cache-dir -e '.[test]' && pytest -q"
```
