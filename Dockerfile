FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CODECOMMIT_JWT_SECRET=change-this-in-production \
    CODECOMMIT_JWT_TTL=86400

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

EXPOSE 8080

CMD ["uvicorn", "src.codecommit.app_v2:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
