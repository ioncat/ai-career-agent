# Quick Start — Docker

## Prerequisites

- VM with Docker + Docker Compose installed
- Git access to this repo
- `.env` file ready (see `.env.example`)
- `fonts/` folder with Segoe UI / Calibri (gitignored — copy manually)

---

## 1. Clone & configure

```bash
git clone <repo-url> career-agent
cd career-agent
```

Copy and fill in secrets:

```bash
cp .env.example .env
nano .env
```

Minimum required in `.env`:

```
TELEGRAM_BOT_TOKEN=...
ANTHROPIC_API_KEY=...
CAREER_AGENT_USER_1=1
```

---

## 2. Prepare feeds

```bash
cp services/job-monitor/feeds.example.json services/job-monitor/feeds.json
# edit feeds.json — add RSS URLs to watch
```

---

## 3. Copy fonts

```bash
# From Windows host → VM (example via scp):
scp -r fonts/ user@vm-ip:~/career-agent/fonts/
```

---

## 4. Start

```bash
docker compose up --build -d
```

First build takes 3–5 min. After that:

```bash
docker compose ps        # all services running?
docker compose logs -f   # watch logs
```

---

## 5. Access

| Service | URL |
|---------|-----|
| Web tracker | `http://<vm-ip>:8080` |
| PDF service | `http://<vm-ip>:8002` |
| Parser | `http://<vm-ip>:8001` |

Telegram bot starts automatically — find it by username and send `/start`.

---

## Common commands

```bash
docker compose stop               # stop all
docker compose up -d              # start (no rebuild)
docker compose up --build -d      # rebuild + start
docker compose logs career-agent  # bot logs
docker compose restart job-monitor
```

## Update

```bash
git pull
docker compose up --build -d
```
