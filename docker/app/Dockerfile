FROM python:3.11-slim
RUN apt-get update && apt-get install -y gdal-bin && rm -rf /var/lib/apt/lists/*
WORKDIR /app
# OJO: el contexto es la RAÍZ del repo (build.context: .), por eso referimos app/...
COPY app/requirements.txt requirements.txt
RUN pip install -r requirements.txt
COPY app/ .
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8000"]
