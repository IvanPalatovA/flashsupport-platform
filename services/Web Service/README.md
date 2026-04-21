# FlashSupport Web Service (MVP)

Web Service delivers React UI and acts as a BFF layer for authentication and chat flows.

## Responsibilities

- serves support chat UI for end users, operators, and admins;
- runs user register/login/refresh through Auth Service;
- validates user and service JWTs before upstream calls;
- refreshes tokens before expiry (user and service flows);
- forwards user and operator messages to Chat Orchestrator;
- allows direct RAG queries for operators;
- keeps temporary role-aware chat state for UI features;
- provides admin review flow for future Knowledge Pipeline integration.

## API (BFF)

- `GET /health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/chats`
- `POST /api/chats`
- `GET /api/chats/:chatId/messages`
- `POST /api/chats/:chatId/messages`
- `POST /api/chats/:chatId/call-operator`
- `POST /api/chats/:chatId/operator-reply`
- `POST /api/chats/:chatId/operator-action`
- `DELETE /api/chats/:chatId`
- `POST /api/rag/search`
- `POST /api/operator/knowledge-requests`
- `GET /api/admin/knowledge-requests`
- `POST /api/admin/knowledge-requests/:requestId/approve`
- `POST /api/admin/knowledge-requests/:requestId/reject`
- `GET /api/admin/accounts`
- `POST /api/admin/accounts/:accountId/block`
- `POST /api/admin/accounts/:accountId/role`

## Environment

Required variables are defined in:

- `.env.example`
- `.env.dev`
- `.env.prod`

Main settings:

- `WEB_SERVICE_ENV` (`dev` or `prod`) - passed from Compose;
- `OPERATOR_CALL_THRESHOLD_MESSAGES` - threshold `N` after which user can call operator;
- `USER_ACCESS_TOKEN_TTL_MINUTES`, `USER_REFRESH_TOKEN_TTL_DAYS`, `SERVICE_ACCESS_TOKEN_TTL_MINUTES` - logged on startup.

## Run via Docker Compose

From repository root (dev):

```bash
docker compose --env-file .env.public.dev -f docker-compose.yml up -d --build
```

For prod:

```bash
docker compose --env-file .env.public.prod -f docker-compose.yml up -d --build
```

Health check:

```bash
curl http://localhost:8060/health
```

Expected response:

```json
{"status":"ok"}
```

## Local run without Docker

```bash
cd "services/Web Service"
npm ci
export WEB_SERVICE_ENV=dev
npm run dev
```

## Build

```bash
cd "services/Web Service"
npm ci
npm run build
npm run start
```
