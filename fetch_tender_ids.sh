#!/bin/sh

URL_SEARCH='https://api.investmoscow.ru/investmoscow/tender/v2/filtered-tenders/searchtenderobjects'
URL_INFO_BASE='https://api.investmoscow.ru/investmoscow/tender/v1/object-info/gettenderobjectinformation?tenderId='

PAGE_SIZE=100
OUT_IDS='ids.txt'
DATA_DIR='data'

BASE_REQ='{
  "orderBy": "Relevance",
  "orderAsc": false,
  "pageNumber": 1,
  "pageSize": 100,
  "objectKinds": ["nsi:tender_type_portal:13"],
  "objectTypes": ["nsi:41:30011568"],
  "tenderStatus": "nsi:tender_status_tender_filter:2"
}'

do_search() {
    req_json=$1
    curl -s "$URL_SEARCH" \
        -H 'content-type: application/json' \
        -H 'accept: application/json' \
        --data-raw "$req_json"
}

do_info() {
    id=$1
    curl -s "${URL_INFO_BASE}${id}" \
        -H 'accept: application/json'
}

mkdir -p "$DATA_DIR"
: >"$OUT_IDS"

probe_req=$(printf '%s\n' "$BASE_REQ" | jq -c '.pageNumber=1 | .pageSize=1')
probe_resp=$(do_search "$probe_req")

totalCount=$(printf '%s\n' "$probe_resp" | jq -r '.totalCount // empty')
if [ -z "$totalCount" ] || [ "$totalCount" = "null" ]; then
    echo "failed to extract .totalCount" >&2
    printf '%s\n' "$probe_resp" | jq . >&2 || true
    exit 1
fi

pages=$(((totalCount + PAGE_SIZE - 1) / PAGE_SIZE))
echo "totalCount=$totalCount pageSize=$PAGE_SIZE pages=$pages" >&2

page=1
while [ "$page" -le "$pages" ]; do
    req_json=$(printf '%s\n' "$BASE_REQ" | jq -c --argjson p "$page" --argjson s "$PAGE_SIZE" \
        '.pageNumber=$p | .pageSize=$s')

    echo "fetch page $page/$pages" >&2
    resp=$(do_search "$req_json")

    ids=$(printf '%s\n' "$resp" | jq -r '.entities[]? .tenders[]? .id')
    if [ -n "$ids" ]; then
        printf '%s\n' "$ids" >>"$OUT_IDS"
    fi

    printf '%s\n' "$ids" | while IFS= read -r id; do
        [ -n "$id" ] || continue
        out_file="${DATA_DIR}/${id}.json"

        if [ -s "$out_file" ]; then
            echo "skip id=$id (exists)" >&2
            continue
        fi

        echo "fetch info id=$id" >&2
        info=$(do_info "$id")

        printf '%s\n' "$info" | jq . >"$out_file" || {
            echo "failed to fetch/parse info for id=$id" >&2
            rm -f "$out_file"
            exit 1
        }
    done

    page=$((page + 1))
done

sort -n "$OUT_IDS" | uniq >ids_unique_sorted.txt

echo "written: $OUT_IDS" >&2
echo "written: ids_unique_sorted.txt" >&2
echo "data saved in: $DATA_DIR/" >&2
