FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn[standard]

COPY app.py /app/app.py

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host=0.0.0.0", "--port=8080"]

