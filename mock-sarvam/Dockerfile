FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir fastapi==0.115.6 uvicorn[standard]==0.34.0 python-multipart==0.0.20
COPY mock-sarvam/app.py ./
EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
