# syntax=docker/dockerfile:1.7
FROM python:3.11.8-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_PREFER_BINARY=1

WORKDIR /app

COPY pyproject.toml ./
RUN python -c "import tomllib; deps = tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']; open('/tmp/requirements.txt', 'w', encoding='utf-8').write('\n'.join(deps) + '\n')"
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install -r /tmp/requirements.txt

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/pip python -m pip install --no-deps .

COPY config ./config

EXPOSE 8080

CMD ["uvicorn", "main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8080"]
