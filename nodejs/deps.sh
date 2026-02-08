#!/bin/sh

say() { printf '%s\n' "$*"; }

if ! command -v curl >/dev/null 2>&1; then
    say "curl not found; installing..."
    sudo apt update
    sudo apt install -y curl ca-certificates
fi

if ! command -v fnm >/dev/null 2>&1; then
    say "Installing fnm..."
    curl -fsSL https://fnm.vercel.app/install | bash
fi

FNM_PATH="$HOME/.local/share/fnm"
if [ -d "$FNM_PATH" ]; then
    PATH="$FNM_PATH:$PATH"
    export PATH
fi

if ! command -v fnm >/dev/null 2>&1; then
    say "ERROR: fnm not found after install. PATH=$PATH"
    exit 1
fi

eval "$(fnm env)"

say "Installing Node 25..."
fnm install 25
fnm use 25

say "Node: $(node -v)"
say "npm : $(npm -v)"

say "Installing Chrome/Puppeteer runtime libraries..."
sudo apt update
sudo apt install -y \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2t64 \
    libnss3 \
    libnspr4 \
    libxshmfence1 \
    libpangocairo-1.0-0 \
    libpango-1.0-0 \
    libcairo2 \
    libgtk-3-0 \
    fonts-liberation \
    xdg-utils

say "Done."
