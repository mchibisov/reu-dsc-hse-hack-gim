FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt requirements.shared.txt ./
COPY database ./database
RUN pip install --no-cache-dir -r requirements.shared.txt
COPY gim ./gim
RUN useradd --uid 10001 --create-home bot && mkdir -p /data/files && chown -R bot:bot /data
USER bot
CMD ["python", "-m", "gim.shared_main", "run"]
