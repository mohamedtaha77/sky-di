FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m appuser
USER appuser

ENV PORT=8501
EXPOSE 8501

CMD ["sh", "-c", "exec streamlit run app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true"]
