#!/bin/bash
# =============================================================================
# setup-user.sh — Create restricted aiuser on VPS
# Run as root
# =============================================================================
set -e

AIUSER="aiuser"
CPANEL_USER="${1:-}"  # Pass your cPanel account username as argument

if [ -z "$CPANEL_USER" ]; then
  echo "Usage: $0 <cpanel-username>"
  echo "Example: $0 mysite"
  exit 1
fi

echo "[*] Creating user: $AIUSER"
useradd -m -s /bin/bash "$AIUSER"
echo "[!] Set a strong password for $AIUSER:"
passwd "$AIUSER"

echo "[*] Creating directories..."
mkdir -p /home/$AIUSER/staging
mkdir -p /home/$AIUSER/logs
mkdir -p /home/$AIUSER/repo.git
mkdir -p /home/$AIUSER/.ssh

chown -R $AIUSER:$AIUSER /home/$AIUSER/
chmod 750 /home/$AIUSER/staging
chmod 750 /home/$AIUSER/logs
chmod 700 /home/$AIUSER/.ssh

echo "[*] Setting up bash history logging..."
cat >> /home/$AIUSER/.bashrc << 'EOF'
export HISTTIMEFORMAT="%F %T "
export HISTFILESIZE=10000
export HISTSIZE=10000
export PROMPT_COMMAND='history -a'
EOF

echo "[*] Adding $AIUSER to $CPANEL_USER group for public_html write access..."
usermod -aG "$CPANEL_USER" "$AIUSER"

echo "[*] Setting group-write on public_html..."
chmod g+w /home/$CPANEL_USER/public_html

echo "[*] Adding sudoers rule for deploy.sh only..."
echo "$AIUSER ALL=(root) NOPASSWD: /home/$AIUSER/deploy.sh" > /etc/sudoers.d/$AIUSER
chmod 440 /etc/sudoers.d/$AIUSER

echo ""
echo "[OK] User $AIUSER created."
echo "[!] Next: add your SSH public key to /home/$AIUSER/.ssh/authorized_keys"
