# FlashSupport Auth Service (MVP)

Единый центр доверия для пользовательской и межсервисной аутентификации.

## Что делает

- регистрирует пользователей (`login` + `password` + `role`);
- выполняет вход пользователя и выдает:
  - `access token` (JWT, 15 минут),
  - `refresh token` (JWT, 15 дней);
- обновляет токены по refresh-token с ротацией;
- выдает сервисный `access token` (JWT, 15 минут) по Signed Assertion;
- хранит логины пользователей как есть (без хеширования), а хеши паролей в зашифрованном виде в PostgreSQL (через `pgcrypto`).

## Signed Assertion

1. Сервис подписывает assertion своим private key.
2. Auth Service проверяет подпись по public key сервиса.
3. При успешной проверке Auth Service выдает сервисный JWT.

Public keys сервисов хранятся в `config/keys/services` и синхронизируются в таблицу `service_public_keys` при старте.

## API

- `GET /health`
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/service-token`

## Environment

Обязательные переменные:

- `AUTH_SERVICE_ENV` (`dev`/`prod`)
- `DATABASE_URL`
- `DATABASE_ENCRYPTION_KEY`
- `AUTH_PRIVATE_KEY_PATH`
- `AUTH_PUBLIC_KEY_PATH`
- `SERVICE_PUBLIC_KEYS_DIR`

TTL настраиваются и логируются при старте:

- `USER_ACCESS_TOKEN_TTL_MINUTES=15`
- `USER_REFRESH_TOKEN_TTL_DAYS=15`
- `SERVICE_ACCESS_TOKEN_TTL_MINUTES=15`

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
curl http://localhost:8070/health
```

Ожидается:

```json
{"status":"ok"}
```

Swagger:

- `http://localhost:8070/docs`

## Локальный запуск (без Docker)

```bash
cd "services/Auth Service"
python -m venv .venv
source .venv/bin/activate
pip install -e .[test]
cp .env.example .env
export AUTH_SERVICE_ENV=dev
uvicorn main:app --app-dir src --host 0.0.0.0 --port 8070
```

## Тесты

```bash
docker run --rm -v "$PWD/services/Auth Service:/work" -w /work python:3.11.8-slim-bookworm sh -lc "python -m pip install --no-cache-dir -e '.[test]' && AUTH_SERVICE_ENV=dev SKIP_SCHEMA_INIT=true pytest -q"
```
