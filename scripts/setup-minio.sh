#!/usr/bin/env bash
# setup-minio.sh — Prepare host for MinIO and create the openwebui bucket
# Run as root on the VPS after adding MINIO_ROOT_USER/PASSWORD to /opt/openwebui/.env

set -euo pipefail

ok()   { echo -e "  \033[92m[OK]\033[0m  $*"; }
err()  { echo -e "  \033[91m[ERR]\033[0m $*"; exit 1; }
info() { echo -e "  \033[1m[..]\033[0m  $*"; }

[ "$(id -u)" = "0" ] || err "Run as root"

ENV_FILE="/opt/openwebui/.env"
DATA_DIR="/opt/minio/data"
COMPOSE_DIR="/opt/openwebui"

# ── 1. Create data directory on real disk ────────────────────────────────────
info "Creating MinIO data directory at $DATA_DIR ..."
mkdir -p "$DATA_DIR"
chmod 750 "$DATA_DIR"
ok "Directory ready — files will be stored on disk at $DATA_DIR"

# ── 2. Check .env has MinIO credentials ──────────────────────────────────────
info "Checking .env for MinIO credentials..."
if ! grep -q "MINIO_ROOT_USER" "$ENV_FILE"; then
    err "MINIO_ROOT_USER not found in $ENV_FILE — add it first:
  echo 'MINIO_ROOT_USER=minioadmin' >> $ENV_FILE
  echo 'MINIO_ROOT_PASSWORD=yourpassword' >> $ENV_FILE"
fi
ok "Credentials found in $ENV_FILE"

# ── 3. Open CSF ports for MinIO console (9001) ───────────────────────────────
# Port 9000 (API) stays bound to 127.0.0.1 — not exposed externally
# Port 9001 (console) opened so you can reach it via browser
info "Opening port 9001 in CSF for MinIO console..."
if grep -q "^TCP_IN" /etc/csf/csf.conf; then
    if ! grep -q "9001" /etc/csf/csf.conf; then
        sed -i 's/^TCP_IN = "\(.*\)"/TCP_IN = "\1,9001"/' /etc/csf/csf.conf
        csf -r >/dev/null 2>&1 && systemctl restart docker >/dev/null 2>&1
        ok "Port 9001 added to CSF TCP_IN and firewall reloaded"
    else
        ok "Port 9001 already in CSF"
    fi
fi

# ── 4. Start MinIO ────────────────────────────────────────────────────────────
info "Starting MinIO container..."
cd "$COMPOSE_DIR"
docker compose up -d minio
sleep 5

# ── 5. Install mc (MinIO client) and create bucket ───────────────────────────
info "Installing mc (MinIO client)..."
if ! command -v mc &>/dev/null; then
    curl -sSL https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc
    chmod +x /usr/local/bin/mc
fi
ok "mc installed"

info "Waiting for MinIO to be ready..."
for i in {1..12}; do
    if curl -sf http://127.0.0.1:9000/minio/health/live >/dev/null 2>&1; then
        ok "MinIO is up"
        break
    fi
    sleep 5
done

# Load credentials from .env
MINIO_USER=$(grep MINIO_ROOT_USER "$ENV_FILE" | cut -d= -f2)
MINIO_PASS=$(grep MINIO_ROOT_PASSWORD "$ENV_FILE" | cut -d= -f2)

info "Configuring mc alias..."
mc alias set local http://127.0.0.1:9000 "$MINIO_USER" "$MINIO_PASS" >/dev/null

info "Creating openwebui bucket..."
if mc ls local/openwebui >/dev/null 2>&1; then
    ok "Bucket 'openwebui' already exists"
else
    mc mb local/openwebui
    ok "Bucket 'openwebui' created"
fi

# ── 6. Restart Open WebUI to pick up S3 env vars ─────────────────────────────
info "Restarting Open WebUI to enable S3 storage..."
docker compose restart open-webui
ok "Open WebUI restarted"

# ── Done ─────────────────────────────────────────────────────────────────────
SERVER_IP=$(curl -s --max-time 5 ifconfig.me || echo "YOUR_SERVER_IP")
echo ""
echo -e "  \033[1mDone.\033[0m"
echo ""
echo "  MinIO console:  http://$SERVER_IP:9001"
echo "  MinIO API:      http://127.0.0.1:9000  (internal only)"
echo "  Data on disk:   $DATA_DIR"
echo "  Bucket:         openwebui"
echo ""
echo "  Open WebUI file uploads now go to MinIO (stored at $DATA_DIR)"
echo ""
