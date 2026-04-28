FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN ln -s /usr/local/bin/python3 /usr/local/bin/python
COPY . .
RUN mkdir -p /app/margo/estado /app/margo/logs
ENV DEEPSEEK_API_KEY=""
ENV PORT=8000
EXPOSE 8000
CMD ["python3", "margo_server.py"]
