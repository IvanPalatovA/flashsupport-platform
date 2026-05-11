# FlashSupport LLM Runtime

Inference-сервис для генерации ответов по инструкциям и top-k контексту от RAG Engine.

## Что делает

- принимает запрос на инференс от RAG Engine;
- проверяет user JWT и service JWT;
- складывает входящие запросы в очередь;
- обрабатывает очередь воркерами с ограничением параллелизма;
- вызывает Ollama и возвращает результат в RAG Engine;
- перед каждым инференсом проходит service-авторизацию в Auth Service (Signed Assertion -> service JWT).

## API

- `GET /health` -> `{ "status": "ok", "queue_depth": 0 }`
- `POST /inference`

Request:

```json
{
  "instruction": "Как сбросить пароль?",
  "contexts": [
    {
      "chunk_id": 1,
      "document_id": 10,
      "document_title": "Password reset guide",
      "chunk_index": 0,
      "score": 0.91,
      "text": "Откройте профиль и выберите сброс пароля"
    }
  ],
  "temperature": 0.2,
  "top_p": 0.9,
  "max_tokens": 512,
  "request_id": "req-123"
}
```

Response:

```json
{
  "request_id": "req-123",
  "model": "llama3.1:8b",
  "answer": "Для сброса пароля откройте профиль и выберите соответствующий пункт.",
  "queue_wait_ms": 12,
  "inference_ms": 186
}
```

## Безопасность

Для `POST /inference` обязательны заголовки:

- `Authorization: Bearer <user_access_jwt>`
- `X-Service-Authorization: Bearer <service_access_jwt>`
- `X-Service-Name: <caller_service_id>`

Сервис допускает вызов только от сервисов из `ALLOWED_CALLER_SERVICE_IDS`.

## Конфигурация

Основные переменные в `.env.dev/.env.prod/.env.example`:

- `LLM_MODEL_NAME`
- `MAX_CONCURRENT_INFERENCES`
- `INFERENCE_QUEUE_CAPACITY`
- `INFERENCE_WAIT_TIMEOUT_SECONDS`
- `OLLAMA_BASE_URL`
- `OLLAMA_REQUEST_TIMEOUT_SECONDS`
- `AUTH_*`, `SERVICE_*`, `USER_ACCESS_TOKEN_AUDIENCE`

## Ключи

- Private key LLM Runtime не должен коммититься (`config/keys/services/llm-runtime.private.pem`).
- Public key LLM Runtime должен быть загружен в Auth Service (`services/Auth Service/config/keys/services/llm-runtime.public.pem` или внешний secrets volume).
- Public key Auth Service для проверки входящих JWT указывается через `AUTH_PUBLIC_KEY_PATH`.

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
curl http://localhost:8100/health
```

## Локальный запуск (без Docker)

```bash
cd "services/LLM Runtime"
python -m venv .venv
source .venv/bin/activate
pip install -e .[test]
export LLM_RUNTIME_ENV=dev
uvicorn main:app --app-dir src --host 0.0.0.0 --port 8100
```

## Тесты

```bash
docker run --rm -v "$PWD/services/LLM Runtime:/work" -w /work python:3.11.8-slim-bookworm sh -lc "python -m pip install --no-cache-dir -e '.[test]' && pytest -q"
```
