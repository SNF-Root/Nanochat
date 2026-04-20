FROM python:3.11-slim

WORKDIR /app

# SAML IdP PEM + allow-list YAML: bind-mount host files here (see compose.yml).
RUN mkdir -p /run/saml /run/config && chmod 755 /run/saml /run/config

RUN apt-get update && apt-get install -y --no-install-recommends \
    pkg-config \
    libxml2-dev \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    && rm -rf /var/lib/apt/lists/*

COPY container_requirements.txt .

RUN pip install --no-cache-dir -r container_requirements.txt

COPY . .

CMD ["/bin/bash"]
