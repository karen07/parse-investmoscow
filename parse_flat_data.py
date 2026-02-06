#!/usr/bin/python3

import csv
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from pyproj import Geod

COORDS_FILE = "renovation_coords.txt"
DATA_DIR = "data"
THR_M = 55.0
OK_STATUSES = {"Признаны состоявшимися", "Единственный участник"}

OUT_CSV = "tenders.csv"

HIST_MIN = 0
HIST_MAX = 100
OUT_SVG = "hist_0_100_step1.svg"
OUT_PNG = "hist_0_100_step1.png"

AREA_BINS = [
    (0, 20),
    (20, 30),
    (30, 40),
    (40, 50),
    (50, 60),
    (60, 80),
    (80, 100),
    (100, 150),
    (150, 10_000),
]

geod = Geod(ellps="WGS84")

_FLOAT_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")


def load_coords(path: str):
    coords = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lat_s, lon_s = line.split(",", 1)
            coords.append((float(lat_s), float(lon_s)))
    return coords


def load_json(path: Path):
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return None
    return json.loads(txt)


def parse_money_rub(s: str | None):
    """
    Надёжно парсит:
      "13 196 000,00 руб." -> 13196000
      "4959760,00"         -> 4959760
      "0,00"               -> 0
    """
    if not s:
        return None
    s = s.replace("\xa0", "").replace(" ", "").strip()
    m = _FLOAT_RE.search(s)
    if not m:
        return None
    num = m.group(0).replace(",", ".")
    try:
        return int(round(float(num)))
    except ValueError:
        return None


def parse_area_m2(s: str | None):
    if not s:
        return None
    s = s.replace("\xa0", " ")
    m = _FLOAT_RE.search(s)
    if not m:
        return None
    val = m.group(0).replace(",", ".")
    try:
        return float(val)
    except ValueError:
        return None


def parse_year_from_date(s: str | None):
    if not s:
        return None
    m = _DATE_RE.search(s)
    if not m:
        return None
    return int(m.group(3))


def build_label_map(obj: dict):
    m = {}
    for item in obj.get("procedureInfo") or []:
        lab = item.get("label")
        if lab is not None:
            m[lab] = item.get("value")
    for item in obj.get("objectInfo") or []:
        lab = item.get("label")
        if lab is not None:
            m[lab] = item.get("value")
    for item in obj.get("visualBlockInfo") or []:
        lab = item.get("label")
        if lab is not None:
            m[lab] = item.get("value")
    return m


def bin_floor_1pct(pct: float) -> int:
    return int(pct // 1.0)


def area_bin(area_m2: float):
    for lo, hi in AREA_BINS:
        if lo <= area_m2 < hi:
            return f"[{lo}..{hi})"
    return "unknown"


def fmt_f(x: float, nd: int = 2) -> str:
    """Float -> строка с запятой (для Excel с ru/de локалью)."""
    return f"{x:.{nd}f}".replace(".", ",")


def save_histogram_svg_png_fixed_0_100(hist: Counter, out_svg: str, out_png: str):
    import matplotlib.pyplot as plt

    xs = list(range(HIST_MIN, HIST_MAX + 1))
    ys = [hist.get(x, 0) for x in xs]

    fig = plt.figure()
    ax = fig.add_subplot(1, 1, 1)
    ax.bar(list(range(len(xs))), ys)

    ax.set_title("Histogram of delta_pct (0..100%, step 1%)")
    ax.set_xlabel("delta_pct bin (%)")
    ax.set_ylabel("count")

    tick_step = 5
    tick_pos = [i for i, x in enumerate(xs) if x % tick_step == 0]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels([str(xs[i]) for i in tick_pos])

    fig.tight_layout()
    fig.savefig(out_svg, format="svg")
    fig.savefig(out_png, dpi=200)
    plt.close(fig)


def summarize_group(name: str, rows: dict):
    print(f"\n# {name}")
    print("key;count;avg_delta_pct;median_delta_pct")
    for k in sorted(rows.keys()):
        vals = rows[k]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        med = statistics.median(vals)
        print(f"{k};{len(vals)};{fmt_f(avg,2)};{fmt_f(med,2)}")


def main():
    coords = load_coords(COORDS_FILE)
    files = sorted(p for p in Path(DATA_DIR).glob("*.json") if p.is_file())

    ratios = []
    deltas_pct = []
    deltas_rub = []

    by_year = defaultdict(list)
    by_area = defaultdict(list)

    hist = Counter({i: 0 for i in range(HIST_MIN, HIST_MAX + 1)})
    underflow = 0
    overflow = 0

    header = [
        "tenderId",
        "year",
        "area_m2",
        "start_price",
        "final_price",
        "ratio",
        "delta_pct",
        "dist_m",
    ]

    rows_written = 0
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fcsv:
        w = csv.writer(fcsv, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)

        for p in files:
            try:
                obj = load_json(p)
                if not obj:
                    continue

                status = (
                    obj.get("sidebar", {})
                    .get("tenderStatusInfo", {})
                    .get("statusText", "")
                )
                if status not in OK_STATUSES:
                    continue

                c = obj.get("mapInfo", {}).get("coords", {})
                lat = c.get("lat")
                lon = c.get("long")
                if lat is None or lon is None:
                    continue
                lat = float(lat)
                lon = float(lon)

                near_dist = None
                for jlat, jlon in coords:
                    _, _, dist_m = geod.inv(lon, lat, jlon, jlat)
                    if dist_m < THR_M:
                        near_dist = dist_m
                        break
                if near_dist is None:
                    continue

                labels = build_label_map(obj)

                start_s = labels.get("Начальная цена за объект") or obj.get(
                    "sidebar", {}
                ).get("startPrice")
                final_s = labels.get("Итоговая цена")

                start = parse_money_rub(start_s)
                final = parse_money_rub(final_s)

                if start is None or start <= 0:
                    continue
                if final is None or final <= 0:
                    continue

                ratio = final / start
                delta_pct = (ratio - 1.0) * 100.0
                delta_rub = final - start

                ratios.append(ratio)
                deltas_pct.append(delta_pct)
                deltas_rub.append(delta_rub)

                year = parse_year_from_date(labels.get("Дата начала приёма заявок"))
                area = parse_area_m2(labels.get("Общая площадь")) or parse_area_m2(
                    labels.get("Площадь объекта")
                )

                if year is not None:
                    by_year[year].append(delta_pct)
                if area is not None:
                    by_area[area_bin(area)].append(delta_pct)

                b = bin_floor_1pct(delta_pct)
                if b < HIST_MIN:
                    underflow += 1
                elif b > HIST_MAX:
                    overflow += 1
                else:
                    hist[b] += 1

                tender_id = obj.get("tenderId", "")
                year_s = "" if year is None else str(year)
                area_s = "" if area is None else fmt_f(area, 2)

                row = [
                    str(tender_id),
                    year_s,
                    area_s,
                    str(start),
                    str(final),
                    fmt_f(ratio, 6),
                    fmt_f(delta_pct, 2),
                    fmt_f(near_dist, 2),
                ]

                w.writerow(row)
                rows_written += 1

            except Exception:
                continue

    print(f"# wrote csv: {OUT_CSV} (rows={rows_written})")

    print("\n# summary")
    if not ratios:
        print("count=0")
        return

    print(f"count={len(ratios)}")
    print(f"avg_ratio={fmt_f(sum(ratios)/len(ratios), 6)}")
    print(f"avg_delta_pct={fmt_f(sum(deltas_pct)/len(deltas_pct), 2)}")
    print(f"avg_delta_rub={round(sum(deltas_rub)/len(deltas_rub))}")
    print(f"median_ratio={fmt_f(statistics.median(ratios), 6)}")
    print(f"median_delta_pct={fmt_f(statistics.median(deltas_pct), 2)}")
    print(f"median_delta_rub={statistics.median(deltas_rub)}")

    print("\n# delta_pct histogram (0..100 step 1%)")
    for lo in range(HIST_MIN, HIST_MAX + 1):
        cnt = hist[lo]
        if cnt:
            print(f"[{lo:3}..{lo+1:3})%: {cnt}")
    print(f"\n# underflow(<0%)={underflow} overflow(>100%)={overflow}")

    summarize_group("delta_pct by year (from 'Дата начала приёма заявок')", by_year)
    summarize_group(
        "delta_pct by area bins (from 'Общая площадь'/'Площадь объекта')", by_area
    )

    try:
        save_histogram_svg_png_fixed_0_100(hist, OUT_SVG, OUT_PNG)
        print(f"\n# wrote: {OUT_SVG} and {OUT_PNG}")
    except ModuleNotFoundError:
        print("\n# matplotlib not installed; skip chart output")
    except Exception as e:
        print(f"\n# chart output failed: {e}")


if __name__ == "__main__":
    main()
