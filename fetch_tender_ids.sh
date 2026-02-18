#!/bin/sh

API_BASE='https://api.investmoscow.ru/investmoscow/tender'
URL_SEARCH="$API_BASE/v2/filtered-tenders/searchtenderobjects"
URL_INFO_BASE="$API_BASE/v1/object-info/gettenderobjectinformation?tenderId="

PAGE_SIZE=100
DATA_DIR='data'

MAX_TRIES=5
SLEEP_BASE=2

BASE_REQ='{
  "orderBy": "Relevance",
  "orderAsc": false,
  "pageNumber": 1,
  "pageSize": 100,
  "objectKinds": ["nsi:tender_type_portal:13"],
  "objectTypes": ["nsi:41:30011568"],
  "tenderStatus": "nsi:tender_status_tender_filter:2"
}'

retry() {
    label=$1
    shift

    i=1
    while :; do
        if "$@"; then
            return 0
        fi

        if [ "$i" -ge "$MAX_TRIES" ]; then
            echo "ERROR: $label failed after $MAX_TRIES tries"
            return 1
        fi

        echo "WARN: $label failed, retry $((i + 1))/$MAX_TRIES"
        sleep $((SLEEP_BASE * i))
        i=$((i + 1))
    done
}

do_search() {
    req_json=$1
    curl -fsSL \
        --connect-timeout 10 \
        --max-time 60 \
        -H 'content-type: application/json' \
        -H 'accept: application/json' \
        --data-raw "$req_json" \
        "$URL_SEARCH" \
        | jq -e .
}

do_info() {
    id=$1
    curl -fsSL \
        --connect-timeout 10 \
        --max-time 60 \
        -H 'accept: application/json' \
        "${URL_INFO_BASE}${id}" \
        | jq -e .
}

mkdir -p "$DATA_DIR"

probe_req=$(printf '%s\n' "$BASE_REQ" | jq -c '.pageNumber=1 | .pageSize=1')
probe_resp=$(retry "search probe" do_search "$probe_req")

totalCount=$(printf '%s\n' "$probe_resp" | jq -r '.totalCount // empty')
filteredCount=$(printf '%s\n' "$probe_resp" | jq -r '.filteredCount // empty')
if [ -z "$totalCount" ] || [ "$totalCount" = "null" ]; then
    echo "ERROR: failed to extract totalCount"
    exit 1
fi

pages=$(((totalCount + PAGE_SIZE - 1) / PAGE_SIZE))
echo "filteredCount=$filteredCount totalCount=$totalCount pageSize=$PAGE_SIZE pages=$pages"

page=1
while [ "$page" -le "$pages" ]; do
    req_json=$(printf '%s\n' "$BASE_REQ" | jq -c \
        --argjson p "$page" \
        --argjson s "$PAGE_SIZE" \
        '.pageNumber=$p | .pageSize=$s')

    echo "fetch page $page/$pages"
    resp=$(retry "search page $page" do_search "$req_json")

    ids=$(printf '%s\n' "$resp" | jq -r '.entities[]? .tenders[]? .id')

    printf '%s\n' "$ids" | while IFS= read -r id; do
        [ -n "$id" ] || continue

        out_file="$DATA_DIR/$id.json"
        if [ -s "$out_file" ]; then
            echo "skip id=$id (exists)"
            continue
        fi

        info=$(retry "info id=$id" do_info "$id")

        printf '%s\n' "$info" >"$out_file"
    done

    page=$((page + 1))
done

echo "data saved in: $DATA_DIR"
