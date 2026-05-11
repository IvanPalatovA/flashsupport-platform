FROM python:3.11.10-slim-bookworm
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY src/ src/
EXPOSE 8085
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8085"]