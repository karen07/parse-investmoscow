#!/bin/sh

base='https://fr.mos.ru/pokupka-nedvizhimosti-dlya-vseh/ajax.php'
qs='?category[]=NEW&status[]=FINISHED&pagesize=100000&map=ren'

out=${1:-renovation_coords.txt}
tmp="${out}.tmp.$$"

cleanup() {
    rm -f "$tmp"
}

trap cleanup HUP INT TERM EXIT

curl -fsSL "$base$qs" \
    | jq -r '.objects.items[].coords|join(",")' >"$tmp"

mv "$tmp" "$out"
trap - HUP INT TERM EXIT

printf 'wrote: %s\n' "$out" >&2
