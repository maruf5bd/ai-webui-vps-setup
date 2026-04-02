# Setup Chat Log — AI Web UI VPS Deployment

Full record of the setup conversation: decisions made, errors encountered, and fixes applied.

---

## 1. Initial Request

**User:** Set up a complete AI system on a cPanel/WHM VPS with CSF firewall.

**Requirements:**
- ChatGPT-style Web UI (Open WebUI) connected to OpenRouter
- Restricted non-root Linux user (`aiuser`) for AI access
- Staging directory workflow — AI writes to `/home/aiuser/staging`, never direct to `public_html`
- `deploy.sh` with PHP lint validation before deployment
- Git bare repo for version control and rollback
- Apache reverse proxy for a subdomain
- Direct IP:port access (`http://151.247.219.203:3000`)
- API integrations: OpenRouter (required), Brave Search (optional), Telegram (optional)
- Safety: no root for AI, directory restrictions, action logging
- GitHub repo for all scripts and configs

**Server details provided:**
- Host: `server2.dnsfordedi.com`
- Root SSH key: `G:\My Drive\project\cpanel\cloud`
- Domain: `forexrobots.co.za`
- OpenRouter API key: `sk-or-v1-...`

---

## 2. Server Environment Check

**Question:** Is CloudLinux installed?

**Finding:** Yes — CloudLinux 8.10 with LVE (Lightweight Virtual Environment) kernel.

**Implications discovered:**
- Docker bridge networks (`br-xxxx`) blocked by CSF firewall
- Standard Docker networking doesn't work — must use `network_mode: host`
- LVE kernel restricts certain syscalls containers rely on

---

## 3. Scripts and Files Created

### scripts/setup-docker-csf.sh
- Adds `DOCKER="1"` to `/etc/csf/csf.conf`
- Adds `docker0` and `br-xxxx` interfaces to `/etc/csf/csf.ignore`
- Opens port 3000 in CSF TCP_IN
- Restarts CSF then Docker

### scripts/setup-user.sh
- Creates `aiuser` system user
- Creates `/home/aiuser/{staging,logs}` directories
- Writes `deploy.sh` (PHP lint + rsync to public_html)
- Configures sudoers: `aiuser` can only run `sudo /home/aiuser/deploy.sh`

### scripts/setup-git.sh
- Initialises bare repo at `/home/aiuser/repo.git`
- Writes `post-receive` hook to auto-checkout pushes to staging
- Prints remote add command for local machine

### scripts/deploy.sh
- PHP lint check on all `.php` files in staging
- rsync staging → `/home/forexrobotsco/public_html`
- Logs every deploy with timestamp to `/home/aiuser/logs/deploy.log`

### config/apache-proxy.conf
- Apache reverse proxy template with WebSocket support
- Proxies `https://SUBDOMAIN/` → `http://127.0.0.1:3000/`
- Includes RewriteRule for `ws://` WebSocket upgrade

### docker-compose.yml
```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    container_name: open-webui
    restart: unless-stopped
    network_mode: host
    environment:
      - PORT=3000
      - HOST=0.0.0.0
      - OPENAI_API_BASE_URL=https://openrouter.ai/api/v1
      - OPENAI_API_KEY=${OPENROUTER_API_KEY}
      - WEBUI_SECRET_KEY=${WEBUI_SECRET_KEY}
      - ENABLE_SIGNUP=false
      - ENABLE_OLLAMA_API=false
      - ENABLE_BASE_MODELS_CACHE=false
      - HF_HUB_OFFLINE=1
      - TRANSFORMERS_OFFLINE=1
      - RAG_EMBEDDING_MODEL_AUTO_UPDATE=false
      - RAG_RERANKING_MODEL_AUTO_UPDATE=false
      - AIOHTTP_CLIENT_TIMEOUT=15
      - AIOHTTP_CLIENT_TIMEOUT_OPENAI_MODEL_LIST=10
    volumes:
      - open-webui-data:/app/backend/data
volumes:
  open-webui-data:
```

---

## 4. Errors Encountered and Fixed

### Error 1 — CSF flushing Docker iptables on restart

**Symptom:** After `csf -r`, Docker containers lost network connectivity.

**Error message:**
```
iptables: No chain/target/match by that name
unable to insert jump to DOCKER-ISOLATION-STAGE-1 rule
```

**Root cause:** CSF rebuilds all iptables rules on restart, wiping Docker's chains.

**Fix:** Restart Docker after every CSF restart to rebuild its iptables chains:
```bash
csf -r && systemctl restart docker
```

Long-term fix: `DOCKER="1"` in `csf.conf` tells CSF to preserve Docker chains.

---

### Error 2 — Docker bridge network blocked by CSF

**Symptom:** `curl http://172.19.0.2:8080` from host returned "Connection refused". Container was healthy but unreachable.

**Root cause:** CSF only had `docker0` in `csf.ignore`. Open WebUI was assigned to `br-05b2c4d44da3` (a custom bridge network), which CSF was blocking.

**Fix:** Switched `docker-compose.yml` to `network_mode: host`. Container now binds directly to the host network stack on port 3000 — no bridge interface needed.

---

### Error 3 — Open WebUI startup hang (asyncio event loop blocked)

**Symptom:** Container reported "healthy" but `curl http://127.0.0.1:3000` returned HTTP 000. Logs froze at:
```
No requirements found in frontmatter.
```

**Investigation:**
- `ss -tnp` showed a `CLOSE-WAIT` connection to `3.173.161.3` (Amazon CloudFront — HuggingFace CDN)
- Read Open WebUI source via `docker exec` — found `lifespan()` startup function
- Found two blocking calls:
  1. `huggingface_hub` checking for model updates (network call to HF CDN)
  2. `get_all_models()` called at startup when `ENABLE_BASE_MODELS_CACHE=true` — waits for OpenRouter to respond, hangs the asyncio loop

**Fix:** Added to `docker-compose.yml`:
```
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
ENABLE_BASE_MODELS_CACHE=false
RAG_EMBEDDING_MODEL_AUTO_UPDATE=false
RAG_RERANKING_MODEL_AUTO_UPDATE=false
```

---

### Error 4 — "You do not have permission to access this resource"

**Symptom:** Opening `http://151.247.219.203:3000` showed the login page but after clicking "Get Started" returned a permission error.

**Root cause:** `ENABLE_SIGNUP=false` was set before any admin account was created. The first registration is supposed to auto-promote to admin, but signup was locked.

**Fix:**
1. Set `ENABLE_SIGNUP=true` in `docker-compose.yml`
2. `docker compose down && docker compose up -d`
3. Registered account — automatically became admin
4. Set `ENABLE_SIGNUP=false` back and restarted

---

### Error 5 — ai.forexrobots.co.za had WordPress installed

**Symptom:** Writing the Apache proxy to `ai.forexrobots.co.za` broke an existing WordPress site on that subdomain.

**Decision:** Use `chat.forexrobots.co.za` instead.

**Actions taken:**
- Removed proxy config from `ai.forexrobots.co.za` (WordPress restored)
- Created new `chat` subdomain in cPanel
- Wrote Apache proxy config to `chat.forexrobots.co.za` userdata directories

---

### Error 6 — chat.forexrobots.co.za not resolving (pending)

**Root cause:** `forexrobots.co.za` uses Cloudflare as authoritative nameservers (`jo.ns.cloudflare.com`, `rob.ns.cloudflare.com`). cPanel creates DNS records in local BIND, but Cloudflare ignores them.

**Fix required (manual):** Add in Cloudflare dashboard:
```
Type: A
Name: chat
IPv4: 151.247.219.203
Proxy: ON (orange cloud)
SSL mode: Full
```

After DNS propagates, run AutoSSL:
```bash
/usr/local/cpanel/bin/autossl_check --user=forexrobotsco
```

---

## 5. Subdomain Setup

### Subdomain chosen: chat.forexrobots.co.za

Apache proxy config placed at:
```
/etc/apache2/conf.d/userdata/ssl/2_4/forexrobotsco/chat.forexrobots.co.za/proxy.conf
/etc/apache2/conf.d/userdata/std/2_4/forexrobotsco/chat.forexrobots.co.za/proxy.conf
```

Apache rebuilt and reloaded:
```bash
/scripts/rebuildhttpdconf
systemctl reload httpd
```

---

## 6. Subdomain Swap Script

**User request:** "I want to change `chat.` to `fx.` — I need a script for that."

**First attempt:** `scripts/change-domain.py` — too complex, handled completely different root domains.

**User correction:** "You didn't get that. I want to change `chat.` to `fx.` — just the prefix on the same domain."

**Final script:** `scripts/swap-subdomain.py`

```bash
# Usage
python3 scripts/swap-subdomain.py --from chat --to fx
# or interactive
python3 scripts/swap-subdomain.py
```

Steps performed by the script:
1. Creates new subdomain in cPanel via `whmapi1`
2. Writes Apache `proxy.conf` for new subdomain (both `std` and `ssl` vhosts)
3. Removes `proxy.conf` from old subdomain
4. Rebuilds Apache config and reloads
5. Tests new URL — prints Cloudflare DNS instructions if no record found

---

## 7. GitHub Repository

Repo: `https://github.com/maruf5bd/ai-webui-vps-setup`

| Commit | Description |
|---|---|
| `b8be6b3` | Initial setup: AI Web UI VPS deployment system |
| `d55e0a8` | Add swap-subdomain.py script |
| `cd6b5de` | docs: add API key change, subdomain swap, and deployment status to README |

---

## 8. Current Deployment State

| Item | Value |
|---|---|
| Server | server2.dnsfordedi.com |
| OS | CloudLinux 8.10 (LVE kernel) |
| cPanel account | forexrobotsco / forexrobots.co.za |
| Direct access | http://151.247.219.203:3000 |
| Domain access | https://chat.forexrobots.co.za (DNS pending in Cloudflare) |
| AI provider | OpenRouter (all models) |
| Docker version | 26.1.3 |
| Open WebUI version | v0.8.12 |

---

## 9. Pending Tasks

- [ ] Add `chat` A record in Cloudflare for `forexrobots.co.za`
- [ ] Run AutoSSL for `chat.forexrobots.co.za` after DNS propagates
- [ ] Add Brave Search API key in Open WebUI Admin Panel → Settings → Web Search
- [ ] Add Telegram bot token (optional)
- [ ] Deploy MCP tool layer (Phase 6)
