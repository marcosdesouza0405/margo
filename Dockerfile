FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /app/margo/estado /app/margo/logs
ENV DEEPSEEK_API_KEY=""
ENV PORT=8000
EXPOSE 8000
CMD ["python", "margo_server.py"]
