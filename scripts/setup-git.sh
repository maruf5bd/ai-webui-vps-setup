#!/bin/bash
# =============================================================================
# setup-git.sh — Initialize bare git repo + staging checkout
# Run as aiuser
# =============================================================================
set -e

STAGING="/home/aiuser/staging"
REPO="/home/aiuser/repo.git"

echo "[*] Initializing bare git repo at $REPO..."
git init --bare "$REPO"

echo "[*] Creating post-receive hook (auto-checkout to staging)..."
cat > "$REPO/hooks/post-receive" << 'EOF'
#!/bin/bash
GIT_WORK_TREE=/home/aiuser/staging git checkout -f main
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Git push received — staging updated" \
  >> /home/aiuser/logs/deploy.log
EOF
chmod +x "$REPO/hooks/post-receive"

echo "[*] Initializing working repo in staging..."
cd "$STAGING"
git init
git remote add origin "$REPO"

echo ""
echo "[OK] Git setup complete."
echo ""
echo "To use from your local machine, add remote:"
echo "  git remote add vps aiuser@YOUR_VPS_IP:/home/aiuser/repo.git"
echo ""
echo "Then push:"
echo "  git push vps main"
