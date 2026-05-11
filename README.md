# flashsupport-platform
Микросервисный on-premise продукт для быстрых RAG-ответов. Полностью локальный. Технический стек подобран таким образом, что система защищена от любых  санкицонных ограничений. Сервис определяет за короткое время (&lt;3 секунд) куда перенаправить запрос, и либо автоматически отвечает клиентам, либо перенаправляет запрос оператору.

Команды
# запустить все сервисы
<!-- для режима DEV -->
docker compose --env-file .env.public.dev -f docker-compose.yml up -d --build


<!-- для режима PROD -->
docker compose --env-file .env.public.prod -f docker-compose.yml up -d --build

# MacBook MPS для RAG embedding

Apple MPS/Metal не доступен внутри обычных Linux-контейнеров Docker Desktop. Чтобы embedding-модель RAG работала на MPS, запускайте остальные сервисы в Docker, а RAG Engine нативно на macOS:

```bash
docker compose --env-file .env.public.dev -f docker-compose.yml -f docker-compose.macos-mps.yml up -d --build
./scripts/run-rag-macos-mps.sh
```

В этом режиме контейнеры `web-service` и `chat-orchestrator` обращаются к RAG Engine на хосте по `http://host.docker.internal:18080`, а сам RAG Engine использует `EMBEDDING_DEVICE=mps`.

# Остановить все сервисы
<!-- если запущено в режиме DEV -->
docker compose --env-file .env.public.dev -f docker-compose.yml down

<!-- если запущено в режиме PROD -->
docker compose --env-file .env.public.prod -f docker-compose.yml down

# Остановить конкретный сервис

<!-- если запущено в режиме DEV -->
docker compose --env-file .env.public.dev -f docker-compose.yml stop rag-service

<!-- если запущено в режиме PROD -->
docker compose --env-file .env.public.prod -f docker-compose.yml stop rag-service
