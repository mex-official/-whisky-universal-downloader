FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN addgroup --system app && adduser --system --ingroup app app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=app:app . .
USER app
HEALTHCHECK --interval=60s --timeout=5s --retries=2 CMD ["python", "healthcheck.py"]
CMD ["python", "bot.py"]
