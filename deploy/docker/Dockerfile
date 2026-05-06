FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md /app/
COPY anchor /app/anchor
COPY docs /app/docs
COPY corpus /app/corpus
COPY eval /app/eval

RUN pip install --upgrade pip \
    && pip install .

EXPOSE 8000

CMD ["uvicorn", "anchor.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]

