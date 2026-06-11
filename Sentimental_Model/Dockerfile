FROM python:3.11-slim

WORKDIR /model

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "export_artifacts.py", "--ticker", "GOOGL", "--model", "gemini31_pro", "--strategy", "v1"]
