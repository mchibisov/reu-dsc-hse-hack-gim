FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml requirements.lock /app/
COPY src /app/src
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps .
COPY supabase /app/supabase
COPY scripts /app/scripts
USER 65532:65532
CMD ["python", "-m", "gim_db.outbox"]
