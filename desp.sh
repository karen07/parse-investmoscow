#!/bin/sh

if [ -f /usr/bin/pacman ]; then
	sudo pacman -S base-devel git nss at-spi2-core libcups libdrm \
		libxcomposite libxdamage libxrandr mesa libxkbcommon pango alsa-lib vim less --noconfirm
fi

if [ -f /usr/bin/apt ]; then
	sudo apt update
	sudo apt install libnss3 unzip libasound2t64 -y
fi

curl -o- https://fnm.vercel.app/install | bash

# fnm install 23
