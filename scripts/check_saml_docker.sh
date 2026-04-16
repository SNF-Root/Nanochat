#!/usr/bin/env bash
# Show where SAML PEMs come from: image build (/app) vs bind-mount (/run/saml).
# Run from the repo root (same directory as compose.yml), after the stack is up:
#   ./scripts/check_saml_docker.sh
# Or pass a container name if you do not use compose defaults:
#   SAML_DOCKER_CONTAINER=prom-server ./scripts/check_saml_docker.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONTAINER="${SAML_DOCKER_CONTAINER:-prom-server}"

echo "== SAML files: build context vs runtime =="
echo ""
echo "1) On the HOST (what compose bind-mounts to /run/saml when SAML_IDP_CERT_HOST_DIR is set):"
HOST_SAML="${SAML_IDP_CERT_HOST_DIR:-./config/saml}"
if [[ -d "$HOST_SAML" ]]; then
  ls -la "$HOST_SAML"
  for f in idp.pem sp-cert.pem sp-key.pem; do
    if [[ -f "$HOST_SAML/$f" ]]; then
      echo "   $f: $(wc -c < "$HOST_SAML/$f") bytes, first line: $(head -1 "$HOST_SAML/$f")"
    else
      echo "   $f: (missing)"
    fi
  done
else
  echo "   Directory not found: $HOST_SAML (set SAML_IDP_CERT_HOST_DIR if different)"
fi

echo ""
echo "2) Inside the CONTAINER (requires running $CONTAINER):"
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
  echo "   No running container named '$CONTAINER'. Start the stack, then re-run."
  echo "   Example: docker compose up -d server"
  exit 0
fi

docker exec "$CONTAINER" sh -lc '
  echo "   --- /run/saml (bind-mount; app uses SAML_IDP_X509_CERT_PATH here) ---"
  if ls /run/saml 2>/dev/null; then
    for f in /run/saml/idp.pem /run/saml/sp-cert.pem /run/saml/sp-key.pem; do
      if [ -f "$f" ]; then
        echo "   $f: $(wc -c < "$f") bytes, first line: $(head -1 "$f")"
      elif [ -d "$f" ]; then
        echo "   $f: ERROR is a directory (Docker created this when a bind-mount target was missing)"
      else
        echo "   $f: (missing)"
      fi
    done
  else
    echo "   /run/saml missing"
  fi
  echo ""
  echo "   --- /app/config/saml (from docker build COPY; not used unless env points here) ---"
  if [ -d /app/config/saml ]; then
    ls -la /app/config/saml 2>/dev/null || true
  else
    echo "   (no /app/config/saml in image)"
  fi
  echo ""
  echo "   --- Relevant SAML_* env (paths only) ---"
  env | grep -E "^SAML_(SP_|IDP_)" | grep -i path | sort || true
'

echo ""
echo "3) What 'docker build' put in the image (optional; image must exist):"
IMG="${SAML_SERVER_IMAGE:-}"
if [[ -z "$IMG" ]] && command -v docker >/dev/null && docker compose config --services 2>/dev/null | grep -qx server; then
  IMG="$(docker compose images -q server 2>/dev/null | head -1 || true)"
fi
if [[ -n "$IMG" ]]; then
  docker run --rm --entrypoint '' "$IMG" sh -lc 'ls -la /app/config/saml 2>/dev/null || echo "No /app/config/saml in this image"' || true
else
  echo "   Skipped (set SAML_SERVER_IMAGE=your:image or run from compose with a built server image)."
fi

echo ""
echo "Note: compose sets SAML_IDP_X509_CERT_PATH=/run/saml/idp.pem."
echo "SP key/cert are read from SAML_SP_PRIVATE_KEY_PATH / SAML_SP_X509_CERT_PATH (or *_PEM env);"
echo "point them at /run/saml/sp-key.pem and /run/saml/sp-cert.pem if those files are on the host mount."
