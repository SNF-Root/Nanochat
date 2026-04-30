#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="db-worker"
TAG="dev"
NETWORK="prom-network"

# Postgres container name on the network
DB_HOST="pgvector-db"
DB_PORT="5432"
DB_USER="user"
DB_PASSWORD="user_pw"
DB_NAME="appdb"

# Default script to run (override by passing a path)
DEFAULT_SCRIPT="sqdb.py"

usage() {
  cat <<USAGE
Usage:
  ./start.sh build
  ./start.sh run [script.py]
  ./start.sh build-run [script.py]
  ./start.sh shell

Examples:
  ./start.sh build
  ./start.sh run scripts/process.py
  ./start.sh build-run
  ./start.sh shell

Notes:
  - Uses bind mount (-v "\$PWD":/app), so code changes do NOT require rebuild for "run".
  - Your DB must be reachable on Docker network: ${NETWORK}
  - App connects to: ${DB_HOST}:${DB_PORT}
  - "shell" starts an interactive container with bash shell
USAGE
}

ensure_network() {
  if ! docker network inspect "${NETWORK}" >/dev/null 2>&1; then
    echo "Network '${NETWORK}' not found. Creating it..."
    docker network create "${NETWORK}" >/dev/null
  fi
}

build_image() {
  echo "Building image ${IMAGE_NAME}:${TAG}..."
  docker build --no-cache -t "${IMAGE_NAME}:${TAG}" .
  echo "Build complete."
}

run_script() {
  local script="${1:-$DEFAULT_SCRIPT}"

  if [[ ! -f "${script}" ]]; then
    echo "Error: script '${script}' not found in current directory: $(pwd)"
    echo "Tip: pass a script path like: ./start.sh run scripts/process.py"
    exit 1
  fi

  ensure_network

  echo "Running ${script} in container on network '${NETWORK}'..."
  echo "Connecting to DB: ${DB_HOST}:${DB_PORT}/${DB_NAME}"

  docker run --rm -it \
    --network "${NETWORK}" \
    -v "$PWD":/app \
    -w /app \
    -e "DB_HOST=${DB_HOST}" \
    -e "DB_PORT=${DB_PORT}" \
    -e "DB_NAME=${DB_NAME}" \
    -e "DB_USER=${DB_USER}" \
    -e "DB_PASSWORD=${DB_PASSWORD}" \
    -e "STANFORD_API_KEY=${STANFORD_API_KEY:-}" \
    -e "STANFORD_BASE_URL=${STANFORD_BASE_URL:-https://aiapi-prod.stanford.edu/v1}" \
    "${IMAGE_NAME}:${TAG}" \
    python "${script}"
}

start_shell() {
  ensure_network

  echo "Starting interactive shell in container on network '${NETWORK}'..."
  echo "Connecting to DB: ${DB_HOST}:${DB_PORT}/${DB_NAME}"
  echo "Current directory mounted at /app"

  docker run --rm -it \
    --network "${NETWORK}" \
    -v "$PWD":/app \
    -w /app \
    -e "DB_HOST=${DB_HOST}" \
    -e "DB_PORT=${DB_PORT}" \
    -e "DB_NAME=${DB_NAME}" \
    -e "DB_USER=${DB_USER}" \
    -e "DB_PASSWORD=${DB_PASSWORD}" \
    -e "STANFORD_API_KEY=${STANFORD_API_KEY:-}" \
    -e "STANFORD_BASE_URL=${STANFORD_BASE_URL:-https://aiapi-prod.stanford.edu/v1}" \
    "${IMAGE_NAME}:${TAG}" \
    /bin/bash
}

main() {
  if [[ "${1:-}" == "" ]]; then
    usage
    exit 1
  fi

  case "$1" in
    build)
      build_image
      ;;
    run)
      shift
      run_script "${1:-$DEFAULT_SCRIPT}"
      ;;
    build-run|run-build)
      shift
      build_image
      run_script "${1:-$DEFAULT_SCRIPT}"
      ;;
    shell)
      start_shell
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
