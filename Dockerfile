FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot

# 루트가 아닌 사용자로 실행. data/ 는 도커 볼륨으로 보존된다.
RUN useradd --create-home --uid 1000 bot && mkdir -p /app/data && chown bot:bot /app/data
USER bot

CMD ["python", "-m", "bot"]
