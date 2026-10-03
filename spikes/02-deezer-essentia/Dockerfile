FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir httpx==0.27.2 essentia==2.1b6.dev1389
COPY *.py ./
ENV PYTHONUNBUFFERED=1
