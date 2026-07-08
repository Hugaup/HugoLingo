FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (separate layer — cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 8000

# entrypoint.sh runs migrations then starts the server
ENTRYPOINT ["sh", "entrypoint.sh"]
