#!/bin/bash
# =============================================================================
# setup-docker-csf.sh — Install Docker and configure CSF compatibility
# Run as root on CentOS/AlmaLinux VPS with cPanel/WHM
# =============================================================================
set -e

echo "[*] Installing Docker..."
yum install -y yum-utils
yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable docker
systemctl start docker

echo "[*] Configuring CSF for Docker compatibility..."

CSF_CONF="/etc/csf/csf.conf"

# Backup CSF config
cp "$CSF_CONF" "${CSF_CONF}.bak.$(date +%Y%m%d)"

# Enable Docker support in CSF
sed -i 's/^DOCKER = "0"/DOCKER = "1"/' "$CSF_CONF"

# Add docker0 interface to CSF ignore (prevents CSF from blocking Docker bridge)
DOCKER_IFACE="docker0"
if ! grep -q "$DOCKER_IFACE" /etc/csf/csf.ignore; then
  echo "# Docker bridge interface" >> /etc/csf/csf.ignore
  echo "$DOCKER_IFACE" >> /etc/csf/csf.ignore
fi

# Note: Port 3000 is NOT opened in TCP_IN
# The WebUI is only accessible via Apache reverse proxy on 443
# If you need direct access from your IP for testing, run:
#   csf -a YOUR.IP.ADDRESS "Temporary WebUI testing access"
echo "[!] Port 3000 is NOT opened publicly (accessed via Apache proxy only)"

echo "[*] Restarting CSF..."
csf -r

echo ""
echo "[OK] Docker installed and CSF configured."
echo "[!] Verify with: docker ps && csf -l"
