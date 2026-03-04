# EC2 Single-Instance Deployment (RDS + Redis)

This runbook matches the current production plan:

- `eu-north-1` region
- One Ubuntu `t3.micro` EC2 for app runtime
- RDS PostgreSQL as managed database
- Redis running locally in Docker on EC2
- FastAPI in Docker (`web` + `worker`)
- Next.js running natively with PM2
- Nginx reverse proxy + Let's Encrypt

## 1) Bootstrap EC2

Clone both repositories to your EC2 instance:

```bash
cd /home/ubuntu
git clone <fast-api-repo-url> fast-api
git clone <ui-repo-url> ui
```

Run the bootstrap script:

```bash
cd /home/ubuntu/fast-api
sudo bash deploy/ec2/bootstrap-ec2.sh
```

Log out and log in again so docker group membership is active.

## 2) Configure Backend Environment

Create backend env from template:

```bash
cd /home/ubuntu/fast-api
cp deploy/ec2/.env.backend.example src/.env
nano src/.env
```

Required values:

- `POSTGRES_PASSWORD` from your RDS credentials
- `SECRET_KEY` (generate with `openssl rand -hex 32`)
- `ADMIN_PASSWORD` (strong password)
- `CORS_ORIGINS` includes `https://aisee.art`

## 3) Start Backend Stack

```bash
cd /home/ubuntu/fast-api
docker compose -f deploy/ec2/docker-compose.ec2.yml up -d --build
```

Create first superuser once:

```bash
docker compose -f deploy/ec2/docker-compose.ec2.yml --profile setup run --rm create_superuser
```

Health check:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

## 4) Configure and Build Frontend

Create frontend env:

```bash
cd /home/ubuntu/ui
cp deploy/ec2/.env.frontend.example .env
nano .env
```

Install and build:

```bash
corepack enable
corepack prepare yarn@4.12.0 --activate
yarn install --immutable
yarn build
```

Start frontend with PM2:

```bash
pm2 start deploy/ec2/ecosystem.config.cjs
pm2 save
pm2 startup systemd -u ubuntu --hp /home/ubuntu
```

App check:

```bash
curl http://127.0.0.1:3000
```

## 5) Nginx Reverse Proxy

```bash
sudo cp /home/ubuntu/fast-api/deploy/ec2/nginx.aisee.conf /etc/nginx/sites-available/aisee.art
sudo ln -sf /etc/nginx/sites-available/aisee.art /etc/nginx/sites-enabled/aisee.art
sudo nginx -t
sudo systemctl reload nginx
```

## 6) TLS With Let's Encrypt

After DNS for `aisee.art` and `www.aisee.art` points to EC2 Elastic IP:

```bash
sudo certbot --nginx -d aisee.art -d www.aisee.art
sudo certbot renew --dry-run
```

## 7) Runtime Operations

Common commands:

```bash
# Backend logs
docker compose -f /home/ubuntu/fast-api/deploy/ec2/docker-compose.ec2.yml logs -f web

# Worker logs
docker compose -f /home/ubuntu/fast-api/deploy/ec2/docker-compose.ec2.yml logs -f worker

# Frontend logs
pm2 logs aisee-ui

# Restart stack
docker compose -f /home/ubuntu/fast-api/deploy/ec2/docker-compose.ec2.yml restart
pm2 restart aisee-ui
```
