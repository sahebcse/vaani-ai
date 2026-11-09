FROM python:3.12-slim AS base
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY vaani vaani
COPY fixtures fixtures
EXPOSE 8080
CMD ["uvicorn", "vaani.main:app", "--host", "0.0.0.0", "--port", "8080"]
