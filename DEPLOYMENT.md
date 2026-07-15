# DXT-1 Production Deployment Guide

This guide describes a practical first production deployment for DXT-1 on one
Linux server. It uses:

- Nginx for HTTPS termination, request limits, and reverse proxying
- one Uvicorn API process
- one DXT conversion worker
- SQLite and job files on a persistent local disk
- systemd to start processes at boot and restart them after failures

This architecture allows many users to upload and monitor jobs concurrently,
while one expensive Demucs/ADTOF conversion runs at a time. It is appropriate
for an initial, moderate-volume deployment. It is not a multi-server design.

## 1. Resolve the licensing gate first

Do not treat deployment as legal clearance. DXT-1 is source-available for
noncommercial use under PolyForm Noncommercial 1.0.0. More importantly, the
ADTOF-PyTorch repository currently publishes no license even though it ports
ADTOF and bundles converted weights. Read `LICENSE.md` and
`THIRD_PARTY_NOTICES.md`, and obtain appropriate clarification or permission
before operating a public service.

You must also decide whether users are allowed to process copyrighted audio and
publish suitable terms of use and a privacy/retention notice. DXT-1 deletes
completed and failed jobs after 24 hours by default.

## 2. Choose a hosting shape

Start with a dedicated virtual machine rather than a serverless web host.
Conversions are long-running, use substantial memory and CPU/GPU, write large
temporary files, and require a continuously running worker.

A reasonable CPU-only starting point is:

- Ubuntu 24.04 LTS or another current Linux distribution
- 4 or more CPU cores
- 16 GB RAM
- 50 GB or more persistent SSD storage
- swap enabled as a safety net, not as a substitute for RAM

Actual needs depend heavily on song length, model choice, traffic, and whether
you use CPU or NVIDIA CUDA. Benchmark representative files before launch. Do
not start multiple conversion workers until measurements show the machine has
enough RAM and compute capacity.

Managed platforms can work only if they support two long-running process types
(web and worker), a shared persistent disk, at least 250 MB uploads, generous
RAM, and long-running ML workloads. If any of those are missing, use a VM or
container host instead.

## 3. Prepare the server

The commands below assume an Ubuntu server and a deployment user named `dxt`.
Run administrative commands from an account with `sudo` access.

```bash
sudo apt update
sudo apt install -y git ffmpeg nginx python3 python3-venv python3-pip
sudo useradd --system --create-home --shell /usr/sbin/nologin dxt
sudo mkdir -p /opt/dxt-1 /var/lib/dxt-1/jobs /var/cache/dxt-1
sudo chown -R dxt:dxt /opt/dxt-1 /var/lib/dxt-1 /var/cache/dxt-1
```

Clone the repository and install its Python environment as `dxt`:

```bash
sudo -u dxt git clone https://github.com/topherPedersen/DXT-1 /opt/dxt-1
sudo -u dxt python3 -m venv /opt/dxt-1/.venv
sudo -u dxt /opt/dxt-1/.venv/bin/python -m pip install --upgrade pip setuptools wheel
sudo -u dxt /opt/dxt-1/.venv/bin/python -m pip install -r /opt/dxt-1/requirements.txt
sudo -u dxt /opt/dxt-1/.venv/bin/python /opt/dxt-1/patch_adtof_compat.py
```

For an NVIDIA server, install the driver and a PyTorch build matching the
server's supported CUDA version by following the official PyTorch selector.
Do not copy a macOS virtual environment to Linux.

## 4. Configure production settings

Create `/etc/dxt-1.env`:

```dotenv
DXT_DATA_DIR=/var/lib/dxt-1
DXT_JOB_RETENTION_HOURS=24
DXT_MAX_ACTIVE_JOBS=100
DXT_WORKER_POLL_SECONDS=1
DXT_STALE_JOB_HOURS=6
HOME=/var/cache/dxt-1
XDG_CACHE_HOME=/var/cache/dxt-1
TORCH_HOME=/var/cache/dxt-1/torch
```

Protect it even though the current settings contain no secrets:

```bash
sudo chown root:dxt /etc/dxt-1.env
sudo chmod 640 /etc/dxt-1.env
```

`DXT_DATA_DIR` must be on persistent storage and writable by both the API and
worker. The cache should also persist so model weights are not downloaded after
every deployment.

## 5. Create the API service

Create `/etc/systemd/system/dxt-api.service`:

```ini
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
```

One API process is normally enough at first because it only saves uploads and
queries SQLite; it no longer performs conversions. If API traffic later becomes
a bottleneck, multiple Uvicorn workers on the same host can share SQLite, but
measure before adding them.

## 6. Create the conversion-worker service

Create `/etc/systemd/system/dxt-worker.service`:

```ini
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
```

Enable and start both processes:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dxt-api dxt-worker
sudo systemctl status dxt-api dxt-worker
curl http://127.0.0.1:8000/api/health
```

The health response should report `"ok": true` and
`"demucs_available": true`.

## 7. Put Nginx and HTTPS in front

Create `/etc/nginx/sites-available/dxt-1`, replacing `dxt.example.com` with
your domain:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name dxt.example.com;

    client_max_body_size 260M;

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
```

Enable it and verify the configuration:

```bash
sudo ln -s /etc/nginx/sites-available/dxt-1 /etc/nginx/sites-enabled/dxt-1
sudo nginx -t
sudo systemctl reload nginx
```

Point the domain's DNS record at the server, then obtain an HTTPS certificate.
On Ubuntu, one common approach is Certbot's Nginx integration:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d dxt.example.com
sudo certbot renew --dry-run
```

Do not expose port 8000 publicly. Allow only SSH, HTTP, and HTTPS through the
server or cloud firewall. HTTPS is required before users upload music.

## 8. Add abuse and privacy controls before announcing the site

The application limits each upload to 250 MB and limits active jobs, but that
is not complete internet abuse protection. Before public launch:

- put the site behind a CDN or web-application firewall with rate limiting
- rate-limit `POST /api/process` more strictly than status/download requests
- monitor disk, RAM, CPU/GPU, queue length, error rate, and conversion duration
- decide whether anonymous use is acceptable or add accounts/API keys
- publish terms covering uploaded audio and a clear 24-hour retention policy
- run the API and worker as the unprivileged `dxt` user
- apply operating-system security updates and restrict SSH access
- consider malware scanning and stronger file validation for untrusted uploads

UUID job URLs are difficult to guess, but they are bearer links, not user
authentication. Anyone who obtains a job URL can check its status or download
its result until cleanup removes it.

## 9. Smoke-test the production deployment

Before inviting users:

1. Open the HTTPS URL and verify fonts and static assets load.
2. Upload a short audio file and confirm the API returns a queued job quickly.
3. Watch the worker log until processing completes.
4. Confirm the download name matches the source name with `.mid` substituted.
5. Submit two files from separate browser sessions and verify one waits in the
   queue while the other is processed.
6. Restart `dxt-api` during a queued job and verify the job remains visible.
7. Check available disk space after conversion and verify retention cleanup.
8. Test an oversized and unsupported upload and confirm each is rejected.

Useful diagnostics:

```bash
sudo journalctl -u dxt-api -f
sudo journalctl -u dxt-worker -f
sudo systemctl status dxt-api dxt-worker nginx
df -h /var/lib/dxt-1 /var/cache/dxt-1
curl https://dxt.example.com/api/health
```

The health endpoint only confirms that the API is alive and Demucs is on the
path. A real short conversion is the meaningful end-to-end health check.

## 10. Deploy updates and roll back

Back up the current commit ID before updating:

```bash
cd /opt/dxt-1
sudo -u dxt git rev-parse HEAD
sudo systemctl stop dxt-api dxt-worker
sudo -u dxt git pull --ff-only
sudo -u dxt .venv/bin/python -m pip install -r requirements.txt
sudo -u dxt .venv/bin/python patch_adtof_compat.py
sudo systemctl start dxt-api dxt-worker
curl http://127.0.0.1:8000/api/health
```

Run the automated tests in a staging environment before production updates:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

To roll back, stop both services, restore a known-good Git commit and matching
dependency environment, and start them again. Do not use destructive Git
commands if the server checkout contains uncommitted changes.

## 11. Know when to redesign for multiple servers

SQLite and local job directories require the API and worker to share one
reliable filesystem. Move to a managed queue (for example Redis-backed jobs),
object storage, and a server database before any of these become true:

- you need API or worker processes on different machines
- one server cannot meet throughput or availability targets
- queue state and files must survive server replacement
- you need independent autoscaling of API and conversion workers
- you need per-user job ownership, quotas, billing, or audit history

Do not place SQLite on a generic network filesystem and assume it behaves like
a local disk. Design and test the distributed architecture explicitly.

## Official deployment references

- FastAPI deployment concepts: https://fastapi.tiangolo.com/deployment/concepts/
- FastAPI containers: https://fastapi.tiangolo.com/deployment/docker/
- Uvicorn deployment: https://www.uvicorn.org/deployment/
- FastAPI HTTPS: https://fastapi.tiangolo.com/deployment/https/
- PyTorch installation selector: https://pytorch.org/get-started/locally/
