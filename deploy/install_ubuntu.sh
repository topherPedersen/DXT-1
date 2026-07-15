#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/dxt-1"
DATA_DIR="/var/lib/dxt-1"
CACHE_DIR="/var/cache/dxt-1"
ENV_FILE="/etc/dxt-1.env"
DOMAIN="_"
EMAIL=""
ENABLE_HTTPS=false
ACKNOWLEDGE_LICENSE=false

usage() {
  cat <<'EOF'
Usage: sudo ./deploy/install_ubuntu.sh [options]

Options:
  --domain DOMAIN       Public domain name, for example dxt.example.com
  --email EMAIL         Email address used by Certbot
  --enable-https        Request and configure a Let's Encrypt certificate
  --acknowledge-adtof-license-risk
                        Confirm that you reviewed THIRD_PARTY_NOTICES.md
  -h, --help            Show this help

Run this script from a clone located at /opt/dxt-1 on Ubuntu 22.04 or 24.04.
HTTPS requires the domain's DNS record to already point to this server.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)
      [[ $# -ge 2 ]] || { echo "--domain requires a value" >&2; exit 2; }
      DOMAIN="$2"
      shift 2
      ;;
    --email)
      [[ $# -ge 2 ]] || { echo "--email requires a value" >&2; exit 2; }
      EMAIL="$2"
      shift 2
      ;;
    --enable-https)
      ENABLE_HTTPS=true
      shift
      ;;
    --acknowledge-adtof-license-risk)
      ACKNOWLEDGE_LICENSE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "Run this installer as root with sudo." >&2
  exit 1
fi

if [[ "$(uname -s)" != "Linux" ]] || ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer supports Ubuntu/Debian systems with apt." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
if [[ "$REPO_DIR" != "$APP_DIR" ]]; then
  echo "Clone DXT-1 into $APP_DIR before running this script." >&2
  echo "Current repository: $REPO_DIR" >&2
  exit 1
fi

if [[ "$DOMAIN" != "_" ]] && [[ ! "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]]; then
  echo "The domain contains unsupported characters." >&2
  exit 2
fi

if $ENABLE_HTTPS && { [[ "$DOMAIN" == "_" ]] || [[ -z "$EMAIL" ]]; }; then
  echo "--enable-https requires both --domain and --email." >&2
  exit 2
fi

if ! $ACKNOWLEDGE_LICENSE; then
  cat >&2 <<'EOF'
Installation stopped: ADTOF-PyTorch currently publishes no license.
Read LICENSE.md and THIRD_PARTY_NOTICES.md and obtain appropriate permission
before operating a public service. Re-run with
--acknowledge-adtof-license-risk only after reviewing that issue.
EOF
  exit 1
fi

echo "Installing Ubuntu system packages..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y curl git ffmpeg nginx python3 python3-pip python3-venv
if $ENABLE_HTTPS; then
  apt-get install -y certbot python3-certbot-nginx
fi

if ! id dxt >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin dxt
fi

install -d -o dxt -g dxt -m 0750 "$DATA_DIR" "$DATA_DIR/jobs" "$CACHE_DIR"
chown -R root:root "$APP_DIR"
chmod -R a+rX "$APP_DIR"

python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("DXT-1 production requires Python 3.10 or newer.")
print(f"Using Python {sys.version.split()[0]}")
PY

echo "Creating the Python environment and installing dependencies..."
systemctl stop dxt-api dxt-worker 2>/dev/null || true
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
"$APP_DIR/.venv/bin/python" "$APP_DIR/patch_adtof_compat.py"

cat >"$ENV_FILE" <<EOF
DXT_DATA_DIR=$DATA_DIR
DXT_JOB_RETENTION_HOURS=24
DXT_MAX_ACTIVE_JOBS=100
DXT_WORKER_POLL_SECONDS=1
DXT_STALE_JOB_HOURS=6
HOME=$CACHE_DIR
XDG_CACHE_HOME=$CACHE_DIR
TORCH_HOME=$CACHE_DIR/torch
EOF
chown root:dxt "$ENV_FILE"
chmod 0640 "$ENV_FILE"

cat >/etc/systemd/system/dxt-api.service <<'EOF'
[Unit]
Description=DXT-1 FastAPI service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=dxt
Group=dxt
WorkingDirectory=/opt/dxt-1
EnvironmentFile=/etc/dxt-1.env
ExecStart=/opt/dxt-1/.venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/dxt-worker.service <<'EOF'
[Unit]
Description=DXT-1 audio conversion worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=dxt
Group=dxt
WorkingDirectory=/opt/dxt-1
EnvironmentFile=/etc/dxt-1.env
ExecStart=/opt/dxt-1/.venv/bin/python worker.py
Restart=on-failure
RestartSec=10
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/nginx/conf.d/dxt-rate-limit.conf <<'EOF'
limit_req_zone $binary_remote_addr zone=dxt_process:10m rate=2r/m;
EOF

cat >/etc/nginx/sites-available/dxt-1 <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name __SERVER_NAME__;

    client_max_body_size 260M;
    limit_req_status 429;

    location = /api/process {
        limit_req zone=dxt_process burst=2 nodelay;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_request_buffering on;
        proxy_read_timeout 120s;
        proxy_pass http://127.0.0.1:8000;
    }

    location / {
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_request_buffering on;
        proxy_read_timeout 120s;
        proxy_pass http://127.0.0.1:8000;
    }
}
EOF
sed -i "s/__SERVER_NAME__/$DOMAIN/g" /etc/nginx/sites-available/dxt-1
ln -sfn /etc/nginx/sites-available/dxt-1 /etc/nginx/sites-enabled/dxt-1
rm -f /etc/nginx/sites-enabled/default

systemctl daemon-reload
systemctl enable dxt-api dxt-worker nginx
nginx -t
systemctl restart dxt-api dxt-worker nginx

echo "Waiting for the API health check..."
healthy=false
for _ in {1..30}; do
  if curl --fail --silent http://127.0.0.1:8000/api/health >/dev/null; then
    healthy=true
    break
  fi
  sleep 1
done
if ! $healthy; then
  echo "The API did not become healthy. Inspect: journalctl -u dxt-api -n 100" >&2
  exit 1
fi

if $ENABLE_HTTPS; then
  echo "Requesting a Let's Encrypt certificate for $DOMAIN..."
  certbot --nginx --non-interactive --agree-tos --redirect \
    --email "$EMAIL" -d "$DOMAIN"
  systemctl reload nginx
fi

echo
echo "DXT-1 installation completed successfully."
if $ENABLE_HTTPS; then
  echo "Open: https://$DOMAIN"
elif [[ "$DOMAIN" != "_" ]]; then
  echo "Open: http://$DOMAIN"
else
  echo "Open the Droplet's public IP address in a browser."
fi
echo "API log:    sudo journalctl -u dxt-api -f"
echo "Worker log: sudo journalctl -u dxt-worker -f"
