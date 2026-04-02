# AI Web UI — VPS Setup (cPanel/WHM + CSF + CloudLinux)

ChatGPT-style Web UI powered by Open WebUI, connected to OpenRouter, deployed on a cPanel/WHM VPS with CloudLinux 8 and CSF firewall.

## Live Deployment

| Item | Value |
|---|---|
| **Server** | server2.dnsfordedi.com |
| **OS** | CloudLinux 8.10 (LVE kernel) |
| **cPanel account** | forexrobotsco / forexrobots.co.za |
| **Direct access** | http://151.247.219.203:3000 |
| **Domain access** | https://chat.forexrobots.co.za (DNS pending) |
| **AI provider** | OpenRouter (all models) |
| **Docker version** | 26.1.3 |
| **Open WebUI version** | v0.8.12 |

## Architecture

```
Internet
    │
    ▼
Cloudflare (DNS proxy + SSL)
    │
    ▼
CSF Firewall (port 80/443/3000 open)
    │
    ▼
cPanel Apache 2.4 (port 443)
    │  reverse proxy (mod_proxy)
    ▼
Open WebUI Docker (0.0.0.0:3000)   ←── network_mode: host
    │
    ▼
OpenRouter API (https://openrouter.ai/api/v1)
    │
    ▼
aiuser (restricted Linux user)
    ├── /home/aiuser/staging/        ← AI reads/writes here
    ├── /home/aiuser/repo.git/       ← bare git repo
    ├── /home/aiuser/logs/           ← action + deploy logs
    └── /home/aiuser/deploy.sh       ← staging → public_html
```

## CloudLinux-Specific Notes

> This setup runs on CloudLinux 8 with LVE kernel. Several standard Docker configurations do not work:

| Issue | Cause | Fix Applied |
|---|---|---|
| Docker bridge networks blocked | CSF blocks `br-xxxx` interfaces | `network_mode: host` |
| Container startup hangs forever | HuggingFace model update call blocks asyncio event loop | `HF_HUB_OFFLINE=1` + `ENABLE_BASE_MODELS_CACHE=false` |
| Docker iptables rules flushed on CSF restart | CSF rebuilds iptables | `DOCKER = "1"` in csf.conf + bridge interfaces in csf.ignore |
| nginx-certbot container crashing | hostkey.com container tries to bind port 80 (owned by Apache) | Leave alone — not our container |

## Quick Start (for a fresh server)

### 1. Clone repo
```bash
git clone https://github.com/maruf5bd/ai-webui-vps-setup.git
cd ai-webui-vps-setup
```

### 2. Fill in API keys
```bash
cp .env.example .env
nano .env
# Add: OPENROUTER_API_KEY, WEBUI_SECRET_KEY (random string)
```

### 3. Run setup scripts as root
```bash
chmod +x scripts/*.sh

# Step 1: Fix CSF for Docker (CloudLinux)
bash scripts/setup-docker-csf.sh

# Step 2: Create restricted aiuser
# Replace 'mysite' with your cPanel account username
bash scripts/setup-user.sh mysite

# Step 3: Start Open WebUI
docker compose up -d
```

### 4. Set up Git + deploy (as aiuser)
```bash
su - aiuser
bash /path/to/scripts/setup-git.sh
```

### 5. Configure Apache proxy for your subdomain
```bash
# Copy proxy.conf into your cPanel vhost userdata directory:
# /etc/apache2/conf.d/userdata/ssl/2_4/CPANEL_USER/chat.yourdomain.com/proxy.conf
# /etc/apache2/conf.d/userdata/std/2_4/CPANEL_USER/chat.yourdomain.com/proxy.conf

/scripts/rebuildhttpdconf
systemctl reload httpd
```

### 6. Create admin account
1. Open `http://YOUR_SERVER_IP:3000`
2. Temporarily set `ENABLE_SIGNUP=true` in docker-compose.yml, restart
3. Register — first account is automatically admin
4. Set `ENABLE_SIGNUP=false`, restart

## Server File Layout

```
/opt/openwebui/
├── docker-compose.yml       ← container definition
└── .env                     ← API keys (chmod 600, root only)

/home/aiuser/
├── staging/                 ← AI working directory
├── repo.git/                ← bare git repo (push target)
├── logs/
│   └── deploy.log           ← all deploy activity
└── deploy.sh                ← staging → public_html

/etc/apache2/conf.d/userdata/ssl/2_4/forexrobotsco/
└── chat.forexrobots.co.za/
    └── proxy.conf           ← reverse proxy to port 3000

/etc/csf/
├── csf.conf                 ← DOCKER="1", port 3000 in TCP_IN
└── csf.ignore               ← docker0 + br-xxxx interfaces listed
```

## Git Workflow

```bash
# On your local machine — add VPS as remote
git remote add vps aiuser@151.247.219.203:/home/aiuser/repo.git

# Push to staging
git push vps main
# → auto-deploys to /home/aiuser/staging via post-receive hook

# Deploy staging → public_html (runs PHP lint first)
ssh aiuser@151.247.219.203 "sudo /home/aiuser/deploy.sh"
```

## Rollback

```bash
# On VPS as aiuser
cd /home/aiuser/staging

git log --oneline          # find the commit to roll back to
git checkout <commit-hash> -- .
sudo /home/aiuser/deploy.sh
```

## API Integrations

| Service | Status | Configure |
|---|---|---|
| OpenRouter (AI models) | **Connected** | `.env` → `OPENROUTER_API_KEY` |
| Brave Search | Pending | Admin Panel → Settings → Web Search |
| Telegram Bot | Pending | Add `TELEGRAM_BOT_TOKEN` to `.env` |
| Cloudflare DNS API | Pending | For auto subdomain management |

## Brave Search Setup

1. Open WebUI → Admin Panel → Settings → Web Search
2. Enable Web Search: **ON**
3. Search Engine: `brave`
4. Brave API Key: paste your key

## Safety

| Rule | Detail |
|---|---|
| No root for AI | `aiuser` has no sudo except `deploy.sh` |
| Staged deploys | Changes go to `/staging` first, never direct to `public_html` |
| PHP lint gate | `php -l` runs on every file before deploy — bad code blocked |
| Deploy log | Every deploy timestamped to `/home/aiuser/logs/deploy.log` |
| Signup locked | `ENABLE_SIGNUP=false` — only admin can add users |
| `.env` locked | `chmod 600`, owned by root |
| Port 3000 | Open publicly — restrict to your IP in CSF if preferred |

## Subdomain DNS (Cloudflare)

Since `forexrobots.co.za` uses Cloudflare nameservers, subdomains must be added in the Cloudflare dashboard — cPanel DNS changes are ignored.

```
Type: A
Name: chat
IPv4: 151.247.219.203
Proxy: ON (orange cloud)
SSL mode: Full
```

## Changing the API Key

To swap the OpenRouter API key (or any env variable):

```bash
# SSH in as root
nano /opt/openwebui/.env
# Edit OPENROUTER_API_KEY=sk-or-v1-...
# Save: Ctrl+O, Enter, Ctrl+X

cd /opt/openwebui
docker compose down && docker compose up -d
```

The `.env` file is `chmod 600` (root-only). Changes take effect after restart.

## Swapping the Subdomain

Use the included Python script to move Open WebUI to a different subdomain prefix
(e.g. `chat.forexrobots.co.za` → `fx.forexrobots.co.za`) without touching the root domain:

```bash
# Interactive
python3 scripts/swap-subdomain.py

# Or with flags
python3 scripts/swap-subdomain.py --from chat --to fx
```

The script will:
1. Create the new subdomain in cPanel via WHM API
2. Write Apache proxy config for the new subdomain
3. Remove the proxy config from the old subdomain
4. Rebuild and reload Apache
5. Test the new URL and print Cloudflare DNS instructions if no record exists

> After swapping, add the new subdomain's A record in Cloudflare manually (cPanel DNS is ignored when Cloudflare is authoritative).

## Deployment Status

| Requirement | Status |
|---|---|
| Open WebUI on OpenRouter | Done — running on port 3000 |
| Docker CloudLinux fixes | Done — `network_mode: host`, HF offline flags |
| Restricted `aiuser` | Done — `setup-user.sh` |
| Staging workflow | Done — `deploy.sh` with PHP lint gate |
| Git bare repo + rollback | Done — `setup-git.sh` + post-receive hook |
| Apache reverse proxy | Done — `apache-proxy.conf` + userdata placement |
| Subdomain swap script | Done — `scripts/swap-subdomain.py` |
| Signup locked | Done — `ENABLE_SIGNUP=false` |
| chat.forexrobots.co.za DNS | Pending — add A record in Cloudflare |
| Brave Search | Pending — Phase 5 |
| MCP tool layer | Pending — Phase 6 |
| Telegram bot | Pending — Phase 7 |

## Roadmap

- [x] Phase 1: CloudLinux + Docker + CSF fix
- [x] Phase 2: Open WebUI live on OpenRouter
- [x] Phase 3: Git bare repo + staging + deploy.sh
- [x] Phase 4: Apache reverse proxy + subdomain
- [ ] Phase 5: Brave Search connected
- [ ] Phase 6: MCP tool layer (file + command access)
- [ ] Phase 7: Telegram bot
- [ ] Phase 8: Cloudflare DNS API automation
