# Deployment (single VPS)

A 2 vCPU / 4 GB Ubuntu 24.04 VPS runs the whole stack. These steps are a guide; they were not executed against a public server
in this project (only the local `docker compose up --build` path was verified — see [TEST_REPORT.md](TEST_REPORT.md)).

## 1. Prepare

```bash
sudo apt update && sudo apt install -y docker.io docker-compose-v2 ufw
sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw allow 8883/tcp && sudo ufw enable
git clone <your repo> plasticloop && cd plasticloop
cp .env.example .env
```

Edit `.env` — **every** value below must change (the API refuses to start in production with the development defaults):

```
ENVIRONMENT=production
DEMO_MODE=false
POSTGRES_PASSWORD=<openssl rand -hex 24>
JWT_SECRET=<openssl rand -hex 48>
MQTT_SERVICE_PASSWORD=<openssl rand -hex 24>
DEMO_DEVICE_SECRET=<openssl rand -hex 24>
COOKIE_SECURE=true
CORS_ORIGINS=https://plasticloop.example.org
API_HOST_PORT=127.0.0.1:8000     # only Caddy talks to the API directly
WEB_HOST_PORT=127.0.0.1:3000
MQTT_HOST_PORT=127.0.0.1:1883    # devices use TLS on 8883 via the broker listener below
```

## 2. TLS with Caddy (web + API docs)

`/etc/caddy/Caddyfile`:

```
plasticloop.example.org {
    encode zstd gzip
    reverse_proxy 127.0.0.1:3000
    @docs path /docs* /api/v1/openapi.json
    reverse_proxy @docs 127.0.0.1:8000
}
```

`sudo apt install caddy && sudo systemctl reload caddy` — Caddy obtains and renews the certificate automatically.
The browser only talks to the web app; `/api/v1/*` is proxied internally by Next.js. Server-sent events pass through because
the API marks them `no-transform`.

## 3. MQTT over TLS for devices

Add a TLS listener to `infra/mosquitto/mosquitto.conf` (certificates from Let's Encrypt via certbot, mounted read-only):

```
listener 8883
certfile /certs/fullchain.pem
keyfile  /certs/privkey.pem
```

Expose `8883:8883` for the mosquitto service, keep 1883 bound to localhost, and give devices the CA certificate
(`set ca_pem ...`, see [ESP32_INTEGRATION.md](ESP32_INTEGRATION.md)).

## 4. Start, migrate, create the first admin

```bash
docker compose up --build -d          # migrations run automatically when the api container starts
docker compose ps                     # all services healthy
curl -s https://plasticloop.example.org/api/v1/health/ready
```

Create the first super admin from the API container (no demo accounts exist in production):

```bash
docker compose exec api python - <<'EOF'
from app.db.session import SessionLocal
from app.models import Organization, User, UserMembership
from app.models.enums import OrgType, RoleKey
from app.security.passwords import hash_password
import getpass
with SessionLocal() as db:
    org = Organization(name="Platform", code="PL-PLATFORM", org_type=OrgType.PLATFORM)
    db.add(org); db.flush()
    u = User(email=input("email: "), full_name=input("name: "), password_hash=hash_password(getpass.getpass("password: ")))
    db.add(u); db.flush()
    db.add(UserMembership(user_id=u.id, organization_id=org.id, role_key=RoleKey.SUPER_ADMIN)); db.commit()
EOF
```

Then create panchayat organisations and send staff invitations from **Users**.

## 5. Backups

```bash
sh infra/scripts/backup.sh                         # backups/<UTC>/db.dump + uploads.tar.gz
sh infra/scripts/restore.sh backups/<UTC>          # asks for confirmation; replaces DB + uploads
```

Schedule with cron (e.g. `0 2 * * * cd /home/ops/plasticloop && sh infra/scripts/backup.sh`), copy backups off the server
(rclone/object storage), keep at least 14 days, and test a restore monthly on a spare machine. The round trip was tested
locally (see the test report).

## 6. Operations

* Logs: `docker compose logs -f api worker` (JSON lines with request IDs).
* Upgrades: `git pull && docker compose up --build -d` (migrations run on start; take a backup first).
* Health: `/api/v1/health/ready` for uptime checks; `/api/v1/health` reports which optional capabilities are active
  (vision adapter, routing distance basis).
* Optional road distances: run an OSRM container with the regional extract and set `OSRM_URL`.
* Scaling beyond one API instance: move the rate limiter to Redis and SSE fan-out to a shared listener first.
