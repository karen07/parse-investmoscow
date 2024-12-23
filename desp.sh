#!/bin/sh

if [ -f /usr/bin/pacman ]; then
	sudo pacman -S nodejs npm base-devel git nss at-spi2-core libcups libdrm \
		libxcomposite libxdamage libxrandr mesa libxkbcommon pango alsa-lib vim less --noconfirm
fi
