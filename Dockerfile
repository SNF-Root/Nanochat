FROM python:3.11-slim

WORKDIR /app

# SAML: bind-mount the host IdP PEM here at runtime (e.g. compose.saml.yml).
RUN mkdir -p /run/saml && chmod 755 /run/saml
# Auth: optional allow-list YAML (e.g. compose.auth.yml).
RUN mkdir -p /run/config && chmod 755 /run/config

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
