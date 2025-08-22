FROM python:3.11-slim

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN apt-get update \
 && apt-get install -y libpq-dev gcc python3-dev \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY . . 

ENV FLASK_APP=src.app:app

CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]

