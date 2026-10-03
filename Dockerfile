FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
COPY assets ./assets
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PORT=8080
CMD ["sh", "-c", "streamlit run app.py --server.address=0.0.0.0 --server.port=${PORT}"]
