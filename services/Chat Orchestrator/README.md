# FlashSupport Chat Orchestrator (MVP)

Chat Orchestrator is responsible for message control in FlashSupport and works only through HTTP contracts.

## Responsibilities

- checks whether one role can send a message to another role;
- stores message history and events through external Persistence API (DB is not embedded here);
- forwards user requests to `RAG Engine`;
- escalates chats to operator queue if user asks for human help;
- allows operator to reply, close, block, resolve chat, or send request to specialist queue;
- allows specialist to approve/reject operator request and trigger knowledge-base update request.

## Roles

- `anonymous_user` - unregistered user;
- `registered_user` - registered user;
- `operator` - support operator;
- `specialist` - knowledge specialist;
- `system` - internal routing target.

## API

- `GET /health` -> service health status.
- `POST /access/check` -> access decision for role-to-role message flow.
- `POST /messages/user` -> incoming user message, route to RAG or operator queue.
- `POST /messages/operator` -> operator reply to user.
- `POST /operator/actions` -> operator action (`close_chat`, `block_chat`, `resolve_chat`, `send_to_specialist_queue`).
- `POST /specialist/reviews` -> specialist decision (`approve` / `reject`).

### Persistence API contract used by this service

All history/queue operations are proxied by HTTP requests to `PERSISTENCE_API_URL`:

- `POST /v1/chats/messages`
- `POST /v1/chats/events`
- `POST /v1/chats/status`
- `POST /v1/queues/operator`
- `POST /v1/queues/specialist`
- `POST /v1/queues/specialist/review`
- `POST /v1/knowledge/updates`

This service does not include SQL database logic on purpose.

## Environment

Main required variables:

- `CHAT_ORCHESTRATOR_ENV` (`dev` or `prod`)
- `RAG_ENGINE_URL`
- `PERSISTENCE_API_URL`
- `DEFAULT_TOP_K`
- `HTTP_TIMEOUT_SECONDS`

Configs are loaded from:

- `config/base.yaml`
- `config/dev.yaml` or `config/prod.yaml`

and overridden by env variables.

## Run via Docker Compose

From repository root:

```bash
docker compose --env-file .env.public.dev -f docker-compose.yml up -d --build
```

For prod:

```bash
docker compose --env-file .env.public.prod -f docker-compose.yml up -d --build
```

Health check:

```bash
curl http://localhost:8090/health
```

Expected response:

```json
{"status":"ok"}
```

Swagger:

- `http://localhost:8090/docs`

## Local run without Docker

```bash
cd "services/Chat Orchestrator"
python -m venv .venv
source .venv/bin/activate
pip install -e .[test]
cp .env.example .env
export CHAT_ORCHESTRATOR_ENV=dev
uvicorn main:app --app-dir src --host 0.0.0.0 --port 8090
```

## Tests

```bash
docker run --rm -v "$PWD/services/Chat Orchestrator:/work" -w /work python:3.11.8-slim-bookworm sh -lc "python -m pip install --no-cache-dir -e '.[test]' && CHAT_ORCHESTRATOR_ENV=dev pytest -q"
```