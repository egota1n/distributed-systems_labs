FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y wait-for-it

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY node.py .

CMD ["sh", "-c", "wait-for-it rabbitmq:5672 --timeout=30 -- python node.py"]