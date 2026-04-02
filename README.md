# AI Web UI — VPS Setup (cPanel/WHM + CSF)

ChatGPT-style Web UI connected to OpenRouter, with controlled agent access to a VPS for file management and deployment.

## Architecture

```
Internet → CSF Firewall → Apache (443) → Open WebUI Docker (127.0.0.1:3000)
                                              ↓
                                      OpenRouter API
                                              ↓
                                   aiuser (restricted)
                                      ↓           ↓
                              /staging/      deploy.sh → /public_html/
```

## Quick Start

### 1. Clone this repo on your VPS
```bash
git clone https://github.com/maruf5bd/ai-webui-vps-setup.git
cd ai-webui-vps-setup
```

### 2. Copy and fill in your API keys
```bash
cp .env.example .env
nano .env
```

### 3. Run setup scripts in order (as root)
```bash
chmod +x scripts/*.sh

# Step 1: Docker + CSF
bash scripts/setup-docker-csf.sh

# Step 2: Create restricted aiuser (replace 'mysite' with your cPanel username)
bash scripts/setup-user.sh mysite

# Step 3: Configure Apache proxy
# Copy config/apache-proxy.conf into WHM (see file for instructions)

# Step 4: Start Open WebUI
docker compose up -d
```

### 4. Git setup (as aiuser)
```bash
su - aiuser
bash /path/to/scripts/setup-git.sh
```

### 5. Deploy script
Edit `scripts/deploy.sh` — replace `CPANEL_USER` with your cPanel username, then:
```bash
cp scripts/deploy.sh /home/aiuser/deploy.sh
chmod +x /home/aiuser/deploy.sh
```

## Scripts

| Script | Purpose | Run as |
|---|---|---|
| `scripts/setup-docker-csf.sh` | Install Docker, configure CSF | root |
| `scripts/setup-user.sh` | Create restricted aiuser | root |
| `scripts/setup-git.sh` | Init bare git repo + staging | aiuser |
| `scripts/deploy.sh` | Validate + sync staging → public_html | aiuser |

## Config Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Open WebUI container definition |
| `config/apache-proxy.conf` | Reverse proxy for ai.yourdomain.com |
| `config/mcp-config.json` | MCP server tool access config |

## API Integrations

- **OpenRouter** — AI models (set in `.env`)
- **Brave Search** — Web search (configure in Open WebUI Admin Panel)
- **Telegram** — Bot token (optional, configure separately)

## Safety

- `aiuser` has no root access
- Deploy requires explicit `sudo /home/aiuser/deploy.sh` (allowlisted in sudoers)
- All deploys logged to `/home/aiuser/logs/deploy.log`
- PHP lint check runs before every deploy
- Open WebUI port 3000 bound to localhost only (not publicly exposed)
- Registration disabled in Open WebUI (`ENABLE_SIGNUP=false`)

## OS Compatibility

Tested on: AlmaLinux 8/9, CentOS 7

> **CloudLinux note:** If CloudLinux is installed, Docker must run as a system user outside LVE. See [CloudLinux + Docker setup notes](docs/cloudlinux-docker.md) (coming soon).

## Roadmap

- [ ] Phase 1: User + Docker + Open WebUI
- [ ] Phase 2: Git + deploy script
- [ ] Phase 3: MCP tool layer
- [ ] Phase 4: Telegram bot
- [ ] Phase 5: Cloudflare DNS API
