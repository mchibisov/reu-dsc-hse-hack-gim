FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home bot && mkdir -p /data/files && chown -R bot:bot /data
COPY gim ./gim
COPY migrations ./migrations
USER bot
CMD ["python", "-m", "gim.main", "worker"]
