#!/bin/sh

base='https://fr.mos.ru/pokupka-nedvizhimosti-dlya-vseh/ajax.php'
qs='?category[]=NEW&status[]=FINISHED&pagesize=100000&map=ren'

curl -fsSL "$base$qs" \
    | jq -r '.objects.items[].coords|join(",")'
