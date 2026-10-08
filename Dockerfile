FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home sports
COPY --chown=sports:sports sportpulse ./sportpulse
USER sports
EXPOSE 8000
CMD ["uvicorn", "sportpulse.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
