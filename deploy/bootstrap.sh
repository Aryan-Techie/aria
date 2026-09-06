#!/usr/bin/env bash
# One-time setup for a fresh Oracle Ubuntu 24.04 (aarch64) box.
#
#   curl -fsSL https://raw.githubusercontent.com/Aryan-Techie/aria/main/deploy/bootstrap.sh | bash
#
# or, having cloned the repo already:  bash deploy/bootstrap.sh
#
# Installs Docker, clears the one firewall rule everybody trips over, and
# clones the repo. It deliberately does NOT start the stack: that needs
# deploy/.env.production, which holds secrets and has to be written by hand.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/Aryan-Techie/aria.git}"
CLONE_DIR="${CLONE_DIR:-$HOME/aria}"

echo "==> Checking architecture"
arch="$(uname -m)"
echo "    $arch  (expected aarch64 on VM.Standard.A1.Flex)"

echo "==> Installing Docker Engine + compose plugin"
if ! command -v docker >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
  echo "    Added $USER to the docker group - log out and back in for it to apply."
else
  echo "    Already installed: $(docker --version)"
fi

# Oracle's Ubuntu image ships iptables REJECT rules for everything except SSH,
# INSIDE the instance, on top of the VCN security list. Opening 80/443 in the
# Oracle console alone is not enough and the symptom is a connection that
# hangs rather than one that is refused - which reads exactly like a DNS or a
# Caddy problem and sends you looking in the wrong place for an hour.
echo "==> Opening ports 80 and 443 on the instance firewall"
sudo iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 1 -p tcp --dport 443 -j ACCEPT
sudo netfilter-persistent save >/dev/null 2>&1 || {
  sudo apt-get install -y iptables-persistent >/dev/null 2>&1
  sudo netfilter-persistent save >/dev/null 2>&1
}
echo "    Saved so they survive a reboot."

echo "==> Cloning the repo"
if [ -d "$CLONE_DIR/.git" ]; then
  git -C "$CLONE_DIR" pull --ff-only
else
  git clone "$REPO_URL" "$CLONE_DIR"
fi

cat <<NEXT

  Done. Next, and this part is by hand because it holds secrets:

    cd $CLONE_DIR
    cp deploy/.env.production.example deploy/.env.production
    nano deploy/.env.production        # domains, generated passwords, API keys

  Then:

    bash deploy/up.sh

NEXT
