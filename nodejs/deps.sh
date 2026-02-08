#!/bin/sh

if ! command -v fnm >/dev/null 2>&1; then
    curl -fsSL https://fnm.vercel.app/install | bash
fi

if [ -x "$HOME/.local/share/fnm/fnm" ]; then
    export PATH="$HOME/.local/share/fnm:$PATH"
elif command -v fnm >/dev/null 2>&1; then
    :
else
    echo "fnm not found after install. Check installation output." >&2
    exit 1
fi

eval "$(fnm env --use-on-cd)"

fnm install 25
fnm use 25
node -v
npm -v

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

echo "Done."
