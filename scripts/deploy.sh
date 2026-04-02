#!/bin/bash
# =============================================================================
# deploy.sh — Sync staging → public_html with validation
# Run as aiuser (sudo allowed for this script only)
# =============================================================================
set -e

STAGING="/home/aiuser/staging"
PUBLIC_HTML="/home/CPANEL_USER/public_html"   # ← replace CPANEL_USER
LOG="/home/aiuser/logs/deploy.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

log() {
  echo "[$TIMESTAMP] $*" | tee -a "$LOG"
}

log "=== Deploy started by $(whoami) ==="

# ------------------------------------------------------------------
# 1. PHP lint check
# ------------------------------------------------------------------
log "Running PHP lint check..."
LINT_ERRORS=0
while IFS= read -r -d '' file; do
  if ! php -l "$file" >> "$LOG" 2>&1; then
    log "LINT ERROR: $file"
    LINT_ERRORS=$((LINT_ERRORS + 1))
  fi
done < <(find "$STAGING" -name "*.php" -print0)

if [ "$LINT_ERRORS" -gt 0 ]; then
  log "PHP lint FAILED ($LINT_ERRORS errors) — aborting deploy"
  exit 1
fi
log "PHP lint passed."

# ------------------------------------------------------------------
# 2. (Optional) npm build check — uncomment if you have a build step
# ------------------------------------------------------------------
# if [ -f "$STAGING/package.json" ]; then
#   log "Running npm build..."
#   cd "$STAGING" && npm run build >> "$LOG" 2>&1
# fi

# ------------------------------------------------------------------
# 3. Sync staging → public_html
# ------------------------------------------------------------------
log "Syncing files to $PUBLIC_HTML..."
rsync -av --delete \
  --exclude='.git' \
  --exclude='*.log' \
  --exclude='.env' \
  "$STAGING/" "$PUBLIC_HTML/" >> "$LOG" 2>&1

# ------------------------------------------------------------------
# 4. Restart PHP-FPM if needed (cPanel managed)
# ------------------------------------------------------------------
# Uncomment if needed:
# log "Restarting PHP-FPM..."
# /usr/local/cpanel/scripts/restartsrv_apache_php_fpm >> "$LOG" 2>&1

log "=== Deploy completed successfully ==="
