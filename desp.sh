#!/bin/sh

if [ -f /usr/bin/pacman ]; then
    sudo pacman -Sy --noconfirm \
        base-devel \
        git \
        nss \
        at-spi2-core \
        libcups \
        libdrm \
        libxcomposite \
        libxdamage \
        libxrandr \
        mesa \
        libxkbcommon \
        pango \
        alsa-lib \
        vim \
        less
fi

if [ -f /usr/bin/apt ]; then
    sudo apt update
    sudo apt install -y \
        libnss3 \
        unzip \
        libasound2t64
fi

curl -o- \
    https://fnm.vercel.app/install \
    | bash

# fnm install 23
