FROM postgis/postgis:16-3.4
RUN apt-get update && apt-get install -y postgresql-16-pgrouting gdal-bin && rm -rf /var/lib/apt/lists/*
# NO COPY initdb here; se monta por volumen desde ./db/initdb
