FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POLARIS_AUTH_MODE=strict

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN useradd --create-home --uid 10001 polaris
USER polaris
EXPOSE 8080
CMD ["uvicorn", "polaris_guidance.app:app", "--host", "0.0.0.0", "--port", "8080"]
