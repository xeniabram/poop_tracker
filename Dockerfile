FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn jinja2 python-multipart

COPY gen_icons.py .
RUN python gen_icons.py

COPY main.py .
COPY templates/ templates/
COPY static/ static/

RUN mkdir -p /data

ENV DB_PATH=/data/poop.db

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
