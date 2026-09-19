# Deployment

A single Ubuntu host running nginx, Postgres and one uvicorn process. Replace
`cerebrumkit.example.com` with your domain and `/var/www/cerebrumkit` with your
path throughout.

## Layout

| What | Where |
| --- | --- |
| Backend code + venv | `/var/www/cerebrumkit/backend` |
| Frontend build (web root) | `/var/www/cerebrumkit/frontend/dist` |
| Secrets | `/var/www/cerebrumkit/backend/.env` (mode 640, owned by `www-data`) |
| Service | `cerebrumkit.service` -> uvicorn on `127.0.0.1:8000` |
| App logs | `/var/log/cerebrumkit/api.log`, `api.err.log` |
| Vhost | `/etc/nginx/sites-available/cerebrumkit.example.com` |
| Database | PostgreSQL, `cerebrumkit` on `127.0.0.1:5432` |

Everything runs as `www-data`; Postgres, nginx and the service start on boot.

## First deployment

```bash
# 1. Database
sudo -u postgres psql -c "CREATE USER cerebrumkit WITH PASSWORD 'change-me'"
sudo -u postgres psql -c "CREATE DATABASE cerebrumkit OWNER cerebrumkit"

# 2. Code
mkdir -p /var/www/cerebrumkit && cd /var/www/cerebrumkit
# copy backend/ and frontend/ here (git clone, scp, rsync - your choice)

# 3. Backend
cd /var/www/cerebrumkit/backend
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env      # DATABASE_URL, SECRET_KEY, model key
./venv/bin/python seed_all.py
chown -R www-data:www-data /var/www/cerebrumkit/backend
chmod 640 .env

# 4. Frontend build
cd /var/www/cerebrumkit/frontend/cerebrumkit-vue
npm ci
VITE_API_URL=https://cerebrumkit.example.com/api npm run build
chown -R www-data:www-data /var/www/cerebrumkit/frontend/dist
```

## systemd

`/etc/systemd/system/cerebrumkit.service`:

```ini
[Unit]
Description=CerebrumKit API
After=network.target postgresql.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/cerebrumkit/backend
ExecStart=/var/www/cerebrumkit/backend/venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**One worker on purpose.** The websocket registry and the in-flight agent tasks
live in process memory, so a second worker would broadcast into a chat it cannot
see.

```bash
systemctl daemon-reload && systemctl enable --now cerebrumkit
systemctl status cerebrumkit
journalctl -u cerebrumkit -n 50
```

## nginx

`/etc/nginx/sites-available/cerebrumkit.example.com`:

```nginx
server {
    listen 80;
    server_name cerebrumkit.example.com;
    root /var/www/cerebrumkit/frontend/dist;

    # The Vue router uses history mode: anything that is not a file is index.html.
    location / {
        try_files $uri $uri/ /index.html;
    }

    # REST and the chat websocket share one prefix; the prefix is stripped.
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 3600s;   # agent runs and websockets are long-lived
    }

    location /.well-known/acme-challenge/ {
        root /var/www/cerebrumkit/frontend/dist;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/cerebrumkit.example.com /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d cerebrumkit.example.com
```

The frontend is built with the API URL `https://cerebrumkit.example.com/api`, so
REST calls and the websocket both go through that prefix.

## Deploying changes

```bash
# Backend
rsync -a backend/app/ root@host:/var/www/cerebrumkit/backend/app/
ssh root@host "chown -R www-data:www-data /var/www/cerebrumkit/backend/app && systemctl restart cerebrumkit"

# Frontend
cd frontend/cerebrumkit-vue
VITE_API_URL=https://cerebrumkit.example.com/api npm run build
rsync -a --delete dist/ root@host:/var/www/cerebrumkit/frontend/dist/
ssh root@host "chown -R www-data:www-data /var/www/cerebrumkit/frontend/dist"
```

### Keep the database rows in step

Tools, skills, agents and the System project live in the database, not in the
code, so a code-only deploy leaves them behind:

- A tool whose **body or spec** changed in development has to be copied into the
  deployed `tools` table, or the server keeps running the old one. Running
  `./venv/bin/python seed_general_tools.py` on the server pushes the shipped
  bodies, and `seed_system_project.py` pushes the `manage_*` ones.
- New rows the code ships with are installed by their seed script - the same
  `seed_all.py` you ran the first time is safe to re-run.

When every table should match a development machine, move the data instead:

```powershell
# On the development machine
backend/venv/Scripts/python.exe backend/export_for_deploy.py
tar -czf cerebrumkit-data.tar.gz -C "$env:TEMP/cerebrumkit-data" .
scp cerebrumkit-data.tar.gz root@host:/root/backups/
```

```bash
# On the server
cd /var/www/cerebrumkit/backend
./venv/bin/python load_for_deploy.py /root/backups/cerebrumkit-data
```

`export_for_deploy.py` takes its column list from the ORM metadata, so a
development database whose schema has drifted still produces a file that fits
the deployed schema. `load_for_deploy.py` loads parent-first, fills
`chats.last_message_id` once messages exist, and moves every sequence past the
highest id it inserted.

## Backups

```bash
PGPASSWORD=change-me pg_dump -h 127.0.0.1 -U cerebrumkit -Fc cerebrumkit > /root/backups/cerebrumkit.dump
```
