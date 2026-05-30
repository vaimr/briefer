FROM python:3.11-slim

RUN pip install --no-cache-dir matrix-nio redis

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

CMD ["python", "bot.py"]
