# flashsupport-platform
Микросервисный on-premise продукт для быстрых RAG-ответов. Полностью локальный. Технический стек подобран таким образом, что система защищена от любых  санкицонных ограничений. Сервис определяет за короткое время (&lt;3 секунд) куда перенаправить запрос, и либо автоматически отвечает клиентам, либо перенаправляет запрос оператору.

Команды
# запустить все сервисы
<!-- MacBook с MPS/Metal -->
./scripts/start-macos-mps.sh

<!-- остальные ОС / обычный Docker -->
./scripts/start-docker.sh

<!-- для режима DEV -->
docker compose --env-file .env.public.dev -f docker-compose.yml up -d --build


<!-- для режима PROD -->
docker compose --env-file .env.public.prod -f docker-compose.yml up -d --build

# MacBook MPS для RAG embedding и Ollama

Apple MPS/Metal не доступен внутри обычных Linux-контейнеров Docker Desktop. Поэтому на MacBook ускорение работает так:

- Ollama запускается нативно на macOS, не в Docker.
- RAG Engine запускается нативно на macOS, чтобы видеть `mps`.
- Остальные сервисы запускаются в Docker и обращаются к macOS через `host.docker.internal`.

Сначала запустите Ollama на MacBook так, чтобы Docker-контейнеры могли к ней подключиться:

```bash
./scripts/run-ollama-macos-mps.sh
```

Если порт `11434` уже занят приложением Ollama, закройте приложение Ollama и запустите скрипт снова.

Затем во втором терминале из корня проекта:

```bash
docker compose --env-file .env.public.dev -f docker-compose.yml -f docker-compose.macos-mps.yml up -d --build --remove-orphans
./scripts/run-rag-macos-mps.sh
```

В этом режиме `llm-runtime` обращается к Ollama на `http://host.docker.internal:11434`, а `web-service` и `chat-orchestrator` обращаются к RAG Engine на `http://host.docker.internal:18080`.

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
