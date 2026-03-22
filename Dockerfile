FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
COPY humane/ humane/
COPY serve.py .
COPY presets/ presets/
RUN pip install --no-cache-dir -e ".[all]"
ENV HUMANE_DB_PATH=/data/humane.db
ENV HUMANE_API_PORT=8765
EXPOSE 8765
VOLUME /data
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8765/api/state || exit 1
CMD ["python", "-m", "humane", "serve"]
