FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app \
    && mkdir -p /app/app/data \
    && chown -R app:app /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app app ./app
RUN chown -R app:app /app/app/data

USER app

EXPOSE 4545

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4545", "--proxy-headers"]
