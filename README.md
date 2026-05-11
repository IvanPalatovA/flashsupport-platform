# flashsupport-platform
Микросервисный on-premise продукт для быстрых RAG-ответов. Полностью локальный. Технический стек подобран таким образом, что система защищена от любых  санкицонных ограничений. Сервис определяет за короткое время (&lt;3 секунд) куда перенаправить запрос, и либо автоматически отвечает клиентам, либо перенаправляет запрос оператору.

Команды
# запустить все сервисы
<!-- для режима DEV -->
docker compose --env-file .env.public.dev -f docker-compose.yml up -d --build

# (опционально) переопределить dev-параметры Postgres
# POSTGRES_DB=flashsupport_dev POSTGRES_USER=flashsupport_dev POSTGRES_PASSWORD=flashsupport_dev

<!-- для режима PROD -->
docker compose --env-file .env.public.prod -f docker-compose.yml up -d --build

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