#!/usr/bin/env python3

import argparse
import html
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

from pyproj import Geod

_FLOAT_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")
geod = Geod(ellps="WGS84")


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Build renovation geo analytics from already downloaded investmoscow JSON files. "
            "The parser does not filter by tender status: status is only shown as a property."
        )
    )
    p.add_argument(
        "--coords",
        default="renovation_coords.txt",
        help="renovation coordinates: lat,lon per line",
    )
    p.add_argument(
        "--data-dir", default="data", help="directory with tender JSON files"
    )
    p.add_argument("--radius", type=float, default=100.0, help="match radius in meters")
    p.add_argument("--out-dir", default=".", help="output directory")
    p.add_argument(
        "--year",
        type=int,
        action="append",
        default=None,
        help="keep only this application-start year; may be used more than once",
    )
    p.add_argument("--year-from", type=int, help="keep tenders with year >= this value")
    p.add_argument(
        "--all-years",
        action="store_true",
        help="disable build-time year filters and embed all years",
    )
    p.add_argument("--year-to", type=int, help="keep tenders with year <= this value")
    p.add_argument(
        "--include-unknown-year",
        action="store_true",
        help="when a year filter is set, also keep tenders where the year could not be parsed",
    )
    p.add_argument(
        "--include-empty-renovation-points",
        action="store_true",
        help="write all renovation points to summary, even without matched tenders",
    )
    args = p.parse_args()
    if args.all_years:
        args.year = []
        args.year_from = None
        args.year_to = None
    elif args.year is None:
        args.year = []
    return args


def load_coords(path: str):
    coords = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                lat_s, lon_s = line.split(",", 1)
                lat = float(lat_s.strip())
                lon = float(lon_s.strip())
            except Exception as e:
                raise ValueError(
                    f"{path}:{line_no}: expected 'lat,lon', got {line!r}"
                ) from e
            coords.append({"renovation_id": len(coords) + 1, "lat": lat, "lon": lon})
    return coords


def load_json(path: Path):
    txt = path.read_text(encoding="utf-8").strip()
    if not txt:
        return None
    return json.loads(txt)


def parse_money_rub(s: str | None):
    if not s:
        return None
    s = s.replace("\xa0", "").replace(" ", "").strip()
    m = _FLOAT_RE.search(s)
    if not m:
        return None
    try:
        return int(round(float(m.group(0).replace(",", "."))))
    except ValueError:
        return None


def parse_area_m2(s: str | None):
    if not s:
        return None
    s = s.replace("\xa0", " ")
    m = _FLOAT_RE.search(s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def parse_date(s: str | None):
    if not s:
        return None
    m = _DATE_RE.search(str(s))
    if not m:
        return None
    day, month, year = m.groups()
    return {"date": f"{day}.{month}.{year}", "year": int(year)}


def build_label_map(obj: dict):
    m = {}
    for section in ("procedureInfo", "objectInfo", "visualBlockInfo"):
        for item in obj.get(section) or []:
            lab = item.get("label")
            if lab is not None:
                m[str(lab)] = item.get("value")
    return m


def first_label(labels: dict, names: list[str]):
    for name in names:
        val = labels.get(name)
        if val not in (None, ""):
            return val
    return None


def first_date_from_labels(
    labels: dict,
    preferred_names: list[str],
    fallback_any_date: bool = False,
):
    # Сначала пробуем ожидаемые поля.
    # Для года можно fallback на любую дату.
    # Для end_date так делать нельзя: start_date станет end_date.
    for name in preferred_names:
        parsed = parse_date(labels.get(name))
        if parsed:
            return parsed["date"], parsed["year"], name
    if fallback_any_date:
        for name, val in labels.items():
            if "дат" not in name.lower():
                continue
            parsed = parse_date(val)
            if parsed:
                return parsed["date"], parsed["year"], name
    return None, None, None


def fmt_num(x, nd=2):
    if x is None:
        return ""
    if isinstance(x, int):
        return str(x)
    return f"{float(x):.{nd}f}".replace(".", ",")


def avg_or_none(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def median_or_none(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def percentile(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    pos = (len(vals) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(vals) - 1)
    frac = pos - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def nearest_renovation(lat: float, lon: float, renovation_points):
    best = None
    best_dist = None
    for rp in renovation_points:
        _, _, dist_m = geod.inv(lon, lat, rp["lon"], rp["lat"])
        if best_dist is None or dist_m < best_dist:
            best = rp
            best_dist = dist_m
    return best, best_dist


def feature_point(lon, lat, props):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": props,
    }


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def extract_address(labels):
    return (
        first_label(
            labels,
            [
                "Адрес объекта",
                "Адрес",
                "Местонахождение объекта",
                "Местоположение объекта",
                "Адрес местонахождения",
            ],
        )
        or ""
    )


def extract_start_price(obj, labels):
    return parse_money_rub(
        first_label(
            labels,
            [
                "Начальная цена за объект",
                "Начальная цена",
                "Стартовая цена",
            ],
        )
        or obj.get("sidebar", {}).get("startPrice")
    )


def extract_final_price(labels):
    return parse_money_rub(
        first_label(
            labels,
            ["Итоговая цена", "Цена продажи", "Конечная цена"],
        )
    )


def extract_area(labels):
    return parse_area_m2(
        first_label(
            labels,
            ["Общая площадь", "Площадь объекта", "Площадь"],
        )
    )


def extract_year_and_dates(labels):
    start_date, year, year_source = first_date_from_labels(
        labels,
        [
            "Дата начала приёма заявок",
            "Дата начала приема заявок",
            "Дата начала подачи заявок",
            "Дата публикации",
            "Дата проведения торгов",
            "Дата торгов",
        ],
        fallback_any_date=True,
    )
    end_date, _, _ = first_date_from_labels(
        labels,
        [
            "Дата окончания приёма заявок",
            "Дата окончания приема заявок",
            "Дата и время окончания приёма заявок",
            "Дата окончания подачи заявок",
        ],
    )
    return year, start_date, end_date, year_source


def year_passes(year, args):
    has_filter = (
        bool(args.year) or args.year_from is not None or args.year_to is not None
    )
    if not has_filter:
        return True
    if year is None:
        return args.include_unknown_year
    if args.year and year not in set(args.year):
        return False
    if args.year_from is not None and year < args.year_from:
        return False
    if args.year_to is not None and year > args.year_to:
        return False
    return True


def price_stage(start_price, final_price):
    if final_price is not None and final_price > 0:
        return "has_final_price"
    if start_price is not None and start_price > 0:
        return "start_price_only"
    return "no_price"


def build_map_html(summary_fc, tenders_fc, radius_m, year_filter_text):
    # Для карты нужен только компактный набор свойств торгов. Геометрия самих
    # торгов и сводный GeoJSON в браузере не используются, поэтому не встраиваем
    # их в HTML: это заметно уменьшает файл и ускоряет первый запуск.
    map_fields = {
        "tenderId",
        "status",
        "year",
        "address",
        "area_m2",
        "start_price",
        "final_price",
        "delta_rub",
        "delta_pct",
        "price_m2_start",
        "price_m2_final",
        "price_stage",
        "applications_start_date",
        "renovation_id",
        "renovation_lat",
        "renovation_lon",
        "dist_m",
        "tender_url",
    }
    tender_rows = []
    for feature in tenders_fc.get("features", []):
        props = feature.get("properties") or {}
        tender_rows.append(
            {k: v for k, v in props.items() if k in map_fields and v is not None}
        )

    tenders_json = json.dumps(
        tender_rows,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    # Не даём данным случайно закрыть HTML-тег script.
    tenders_json = (
        tenders_json.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    radius_s = html.escape(f"{radius_m:g}")
    year_s = html.escape(year_filter_text)

    template = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <title>Реновация: карта торгов</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    :root {
      --map-panel-width: 414px;
    }
    html,
    body,
    #map {
      height: 100%;
      margin: 0;
    }
    .map-panel {
      box-sizing: border-box;
      background: white;
      padding: 10px 12px;
      border: 0;
      border-radius: 8px;
      box-shadow: 0 1px 8px rgba(0, 0, 0, .18);
      font: 13px/1.35 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    /*
     * Один и тот же класс стоит на левой информационной панели, фильтрах и
     * списке слоёв. Поэтому их внешняя ширина совпадает пиксель в пиксель.
     */
    .leaflet-control.fixed-map-panel {
      width: var(--map-panel-width) !important;
      min-width: var(--map-panel-width) !important;
      max-width: var(--map-panel-width) !important;
      inline-size: var(--map-panel-width) !important;
      min-inline-size: var(--map-panel-width) !important;
      max-inline-size: var(--map-panel-width) !important;
    }
    @media (max-width: 860px) {
      :root {
        --map-panel-width: calc(50vw - 20px);
      }
    }
    .loading-status-control {
      min-width: 230px;
      background: rgba(255, 255, 255, .96);
      padding: 7px 10px;
      border-radius: 6px;
      box-shadow: 0 1px 8px rgba(0, 0, 0, .18);
      font: 13px/1.35 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .info-panel {
      font-size: 14px;
    }
    .info-panel h1 {
      margin: 0 0 8px;
      font-size: 16px;
    }
    .legend-row {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 4px 0;
    }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      display: inline-block;
    }
    .small {
      color: #555;
      font-size: 12px;
    }
    .leaflet-popup-content {
      min-width: 340px;
      max-width: 520px;
    }
    .leaflet-popup-content table {
      border-collapse: collapse;
      width: 100%;
    }
    .leaflet-popup-content td {
      padding: 2px 7px 2px 0;
      vertical-align: top;
    }
    .leaflet-popup-content td:first-child {
      color: #444;
      white-space: nowrap;
    }
    .popup-title {
      font-weight: 700;
      margin-bottom: 8px;
    }
    .popup-muted {
      color: #666;
      font-size: 12px;
      margin: 4px 0 8px;
    }
    .tender-list {
      max-height: min(440px, calc(100vh - 300px));
      overflow-y: auto;
      padding-right: 4px;
    }
    .tender-card {
      border: 1px solid #ddd;
      border-radius: 8px;
      margin: 6px 0;
      background: #fff;
    }
    .tender-card summary {
      cursor: pointer;
      padding: 7px 9px;
      font-weight: 600;
      list-style-position: inside;
    }
    .tender-card table {
      border-top: 1px solid #eee;
      margin: 0;
      padding: 5px 8px;
    }
    .tender-card-inner {
      padding: 6px 8px 8px;
    }
    .group-marker {
      display: flex;
      align-items: center;
      justify-content: center;
      border-radius: 50%;
      border: 2px solid white;
      color: white;
      font: 700 12px/1 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      box-shadow: 0 1px 5px rgba(0, 0, 0, .35);
    }
    .group-marker.single {
      width: 14px;
      height: 14px;
    }
    .group-marker.multi {
      width: 28px;
      height: 28px;
    }
    .price-filter-control {
      font: 13px/1.35 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    .price-filter-title {
      font-weight: 700;
      margin-bottom: 6px;
    }
    .price-filter-control label {
      display: block;
      margin-top: 6px;
      margin-bottom: 3px;
    }
    .price-filter-row {
      display: flex;
      gap: 6px;
    }
    .price-filter-row input {
      flex: 1 1 0;
      width: auto;
      min-width: 0;
      box-sizing: border-box;
      padding: 3px 5px;
    }
    .price-filter-control select {
      width: 100%;
      box-sizing: border-box;
      padding: 3px 5px;
    }
    .price-filter-control button {
      margin-top: 8px;
      padding: 3px 8px;
    }
    .leaflet-control-layers.map-panel,
    .leaflet-control-layers-expanded.map-panel {
      padding: 10px 12px;
      font: 13px/1.35 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
  </style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
// Сначала показываем саму карту и индикатор. Большой массив торгов читается
// уже после первого кадра, поэтому вместо белого зависшего окна пользователь
// сразу видит подложку карты и текущий этап загрузки.
const map = L.map('map', {
  zoomControl: false,
}).setView([55.751244, 37.618423], 10);

L.control.zoom({
  position: 'bottomright',
}).addTo(map);

L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors',
}).addTo(map);

const startupStatusControl = L.control({ position: 'bottomleft' });
startupStatusControl.onAdd = function onAdd() {
  const div = L.DomUtil.create('div', 'loading-status-control');
  div.textContent = 'Загрузка данных торгов...';
  window.mapLoadingStatusElement = div;
  return div;
};
startupStatusControl.addTo(map);
window.mapLoadingStatusControl = startupStatusControl;
</script>
<script id="tender-data" type="application/json">__TENDERS_JSON__</script>
<script>
let tenderData = [];
const BLANK = '-';

function esc(v) {
  if (v === null || v === undefined || v === '') return BLANK;
  return String(v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function rub(v) {
  if (v === null || v === undefined || v === '') return BLANK;
  const n = Number(v);
  if (!Number.isFinite(n)) return BLANK;
  return new Intl.NumberFormat('ru-RU').format(Math.round(n)) + ' руб.';
}

function num(v, digits = 2) {
  if (v === null || v === undefined || v === '') return BLANK;
  const n = Number(v);
  if (!Number.isFinite(n)) return BLANK;
  return n.toLocaleString('ru-RU', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function row(k, v) {
  return `<tr><td>${esc(k)}</td><td>${v}</td></tr>`;
}

function colorByStage(stage) {
  if (stage === 'has_final_price') return '#2b8cbe';
  if (stage === 'start_price_only') return '#f16913';
  return '#777';
}

function colorByTenders(tenders) {
  const stages = new Set(tenders.map(t => t.price_stage));
  if (stages.size === 1) return colorByStage(tenders[0].price_stage);
  return '#7b3294';
}

function stageName(stage) {
  if (stage === 'has_final_price') return 'есть итоговая цена';
  if (stage === 'start_price_only') return 'только начальная цена';
  return 'нет цены';
}

function tenderUrl(p) {
  if (!p.tender_url) return BLANK;
  const url = esc(p.tender_url);
  return `<a href="${url}" target="_blank" rel="noopener">карточка торгов</a>`;
}

function popupTenderTable(p) {
  const area = p.area_m2 ? num(p.area_m2, 2) + ' м2' : BLANK;
  const growth = p.delta_pct != null ? num(p.delta_pct, 2) + ' %' : BLANK;
  const startM2 = p.price_m2_start != null ? rub(p.price_m2_start) : BLANK;
  const finalM2 = p.price_m2_final != null ? rub(p.price_m2_final) : BLANK;
  const dist = p.dist_m != null ? num(p.dist_m, 1) + ' м' : BLANK;
  const rows = [
    row('Tender ID', esc(p.tenderId)),
    row('Статус', esc(p.status)),
    row('Год', esc(p.year)),
    row('Дата', esc(p.applications_start_date)),
    row('Адрес', esc(p.address)),
    row('Площадь', area),
    row('Начальная цена', rub(p.start_price)),
    row('Итоговая цена', rub(p.final_price)),
    row('Рост', growth),
    row('Delta руб.', rub(p.delta_rub)),
    row('Цена старт / м2', startM2),
    row('Цена итог / м2', finalM2),
    row('Расстояние до реновации', dist),
    row('Ссылка', tenderUrl(p)),
  ];
  return `<table>${rows.join('')}</table>`;
}

function tenderSummary(p) {
  const area = p.area_m2 ? `${num(p.area_m2, 2)} м2` : BLANK;
  const startPrice = p.start_price ? rub(p.start_price) : BLANK;
  const finalPrice = p.final_price ? rub(p.final_price) : '';
  return `${area} - ${startPrice} - ${finalPrice}`;
}

function countStages(tenders) {
  const c = { has_final_price: 0, start_price_only: 0, no_price: 0 };
  for (const t of tenders) c[t.price_stage] = (c[t.price_stage] || 0) + 1;
  return c;
}

const priceFilters = {
  priceMin: null,
  priceMax: null,
  priceM2Min: null,
  priceM2Max: null,
};

let selectedYear = null;

function tenderYearValue(p) {
  const y = Number(p.year);
  return Number.isInteger(y) ? y : null;
}

function availableYears() {
  const years = new Set();
  for (const p of tenderData) {
    const y = tenderYearValue(p || {});
    if (y !== null) years.add(y);
  }
  return Array.from(years).sort((a, b) => a - b);
}

function hasUnknownYear() {
  return tenderData.some(p => tenderYearValue(p || {}) === null);
}

function defaultYearFilterValue(years) {
  const currentYear = new Date().getFullYear();
  if (years.includes(currentYear)) return String(currentYear);
  return 'all';
}

function parseYearFilterValue(value) {
  if (value === 'all') return null;
  if (value === 'unknown') return 'unknown';
  const y = Number(value);
  return Number.isInteger(y) ? y : null;
}

function yearFilterLabel() {
  if (selectedYear === null) return 'все годы';
  if (selectedYear === 'unknown') return 'без года';
  return String(selectedYear);
}

function updateYearFilterLabel() {
  const el = document.getElementById('current-year-filter');
  if (el) el.textContent = yearFilterLabel();
}

function tenderPassesYearFilter(p) {
  if (selectedYear === null) return true;
  const y = tenderYearValue(p);
  if (selectedYear === 'unknown') return y === null;
  return y === selectedYear;
}

function fillYearFilterSelect(select) {
  const years = availableYears();
  select.innerHTML = '';

  const all = document.createElement('option');
  all.value = 'all';
  all.textContent = 'Все годы';
  select.appendChild(all);

  for (const year of years) {
    const opt = document.createElement('option');
    opt.value = String(year);
    opt.textContent = String(year);
    select.appendChild(opt);
  }

  if (hasUnknownYear()) {
    const unknown = document.createElement('option');
    unknown.value = 'unknown';
    unknown.textContent = 'Без года';
    select.appendChild(unknown);
  }

  select.value = defaultYearFilterValue(years);
  selectedYear = parseYearFilterValue(select.value);
  updateYearFilterLabel();
}

function effectivePrice(p) {
  if (p.final_price !== null && p.final_price !== undefined) {
    return Number(p.final_price);
  }
  if (p.start_price !== null && p.start_price !== undefined) {
    return Number(p.start_price);
  }
  return null;
}

function effectivePriceM2(p) {
  if (p.price_m2_final !== null && p.price_m2_final !== undefined) {
    return Number(p.price_m2_final);
  }
  if (p.price_m2_start !== null && p.price_m2_start !== undefined) {
    return Number(p.price_m2_start);
  }
  return null;
}

function passesRange(value, minValue, maxValue) {
  if (minValue === null && maxValue === null) return true;
  if (value === null || value === undefined) return false;
  const n = Number(value);
  if (!Number.isFinite(n)) return false;
  if (minValue !== null && n < minValue) return false;
  if (maxValue !== null && n > maxValue) return false;
  return true;
}

function tenderPassesPriceFilters(p) {
  return (
    passesRange(effectivePrice(p), priceFilters.priceMin, priceFilters.priceMax)
    && passesRange(
      effectivePriceM2(p),
      priceFilters.priceM2Min,
      priceFilters.priceM2Max
    )
  );
}

function tenderIsVisible(p) {
  return (
    stageVisible[p.price_stage]
    && tenderPassesYearFilter(p)
    && tenderPassesPriceFilters(p)
  );
}

function visibleTenderFeatures() {
  return tenderData.filter(p => tenderIsVisible(p || {}));
}

function groupVisibleTendersByRenovation() {
  const groups = new Map();

  for (const p of visibleTenderFeatures()) {
    const id = String(p.renovation_id || '');
    const lat = Number(p.renovation_lat);
    const lon = Number(p.renovation_lon);

    if (!id || !Number.isFinite(lat) || !Number.isFinite(lon)) {
      continue;
    }

    if (!groups.has(id)) {
      groups.set(id, {
        renovation_id: id,
        lat,
        lon,
        tenders: [],
      });
    }

    groups.get(id).tenders.push(p);
  }

  const result = Array.from(groups.values());
  for (const group of result) {
    group.tenders.sort((a, b) => {
      const da = a.dist_m == null ? 999999 : Number(a.dist_m);
      const db = b.dist_m == null ? 999999 : Number(b.dist_m);
      if (da !== db) return da - db;
      return String(a.tenderId).localeCompare(String(b.tenderId));
    });
  }

  result.sort((a, b) => Number(a.renovation_id) - Number(b.renovation_id));
  return result;
}

function avgValue(values) {
  const xs = values.filter(v => v !== null && v !== undefined);
  if (xs.length === 0) return null;
  return xs.reduce((a, b) => a + Number(b), 0) / xs.length;
}

function medianValue(values) {
  const xs = values
    .filter(v => v !== null && v !== undefined)
    .map(v => Number(v))
    .sort((a, b) => a - b);
  if (xs.length === 0) return null;
  const mid = Math.floor(xs.length / 2);
  if (xs.length % 2) return xs[mid];
  return (xs[mid - 1] + xs[mid]) / 2;
}

function popupRenovationArea(group, tenders) {
  const counts = countStages(tenders);
  const deltas = tenders
    .filter(t => t.delta_pct !== null && t.delta_pct !== undefined)
    .map(t => Number(t.delta_pct));
  const avgGrowth = avgValue(deltas);
  const medGrowth = medianValue(deltas);
  const rows = [
    row('Точка реновации', esc(group.renovation_id)),
    row('Всего торгов', esc(tenders.length)),
    row('С итоговой ценой', esc(counts.has_final_price)),
    row('Только стартовая цена', esc(counts.start_price_only)),
    row('Без цены', esc(counts.no_price)),
    row(
      'Средний рост цены',
      avgGrowth !== null ? num(avgGrowth, 2) + ' %' : BLANK
    ),
    row(
      'Медианный рост цены',
      medGrowth !== null ? num(medGrowth, 2) + ' %' : BLANK
    ),
  ].join('');
  const cards = tenders.map(t => (
    `<details class="tender-card">`
    + `<summary>${tenderSummary(t)}</summary>`
    + `<div class="tender-card-inner">${popupTenderTable(t)}</div>`
    + `</details>`
  )).join('');
  return [
    '<div class="popup-title">Окрестность точки реновации</div>',
    '<table>',
    rows,
    '</table>',
    '<div class="popup-title" style="margin-top:10px;">Торги в радиусе</div>',
    '<div class="tender-list">',
    cards || '<div class="small">Нет торгов по текущим фильтрам.</div>',
    '</div>',
  ].join('');
}

function areaIcon(count, color) {
  const text = count > 0 ? count : '';
  const html = [
    `<div class="group-marker multi" style="background:${color}">`,
    `${text}</div>`,
  ].join('');
  return L.divIcon({
    className: '',
    html,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    popupAnchor: [0, -16],
  });
}

function syncTopPanelHeights() {
  const info = document.querySelector('.info-panel');
  const filters = document.querySelector('.price-filter-control');
  if (!info || !filters) return;

  // Сначала снимаем ранее выставленную высоту, чтобы корректно пересчитать
  // размер после изменения ширины окна, масштаба браузера или шрифтов.
  info.style.height = '';
  filters.style.height = '';

  const height = Math.ceil(Math.max(
    info.getBoundingClientRect().height,
    filters.getBoundingClientRect().height,
  ));

  info.style.height = `${height}px`;
  filters.style.height = `${height}px`;
}

let panelResizeTimer = null;
window.addEventListener('resize', () => {
  window.clearTimeout(panelResizeTimer);
  panelResizeTimer = window.setTimeout(syncTopPanelHeights, 80);
});

function createInfoControl() {
  const control = L.control({ position: 'topleft' });
  control.onAdd = function onAdd() {
    const div = L.DomUtil.create('div', 'map-panel fixed-map-panel info-panel');
    div.innerHTML = [
      '<h1>Реновация и торги Invest Moscow</h1>',
      '<div>Радиус привязки: <b>__RADIUS__ м</b></div>',
      '<div>Год на карте: <b id="current-year-filter">...</b></div>',
      '<div class="legend-row">',
      '<span class="swatch" style="background:#2b8cbe"></span>',
      'Окрестность: есть итоговая цена',
      '</div>',
      '<div class="legend-row">',
      '<span class="swatch" style="background:#f16913"></span>',
      'Окрестность: только начальная цена',
      '</div>',
      '<div class="legend-row">',
      '<span class="swatch" style="background:#777"></span>',
      'Окрестность: нет цены в JSON',
      '</div>',
      '<div class="legend-row">',
      '<span class="swatch" style="background:#7b3294"></span>',
      'Окрестность: смешанные торги',
      '</div>',
      '<div class="small" style="margin-top:8px;">',
      'Один круг - одна точка реновации. Цвет круга показывает состав ',
      'торгов внутри заданного радиуса. Фильтры справа сверху меняют ',
      'год, цены, круги и содержимое списков.',
      '</div>',
    ].join('');

    L.DomEvent.disableClickPropagation(div);
    L.DomEvent.disableScrollPropagation(div);
    return div;
  };
  return control;
}

createInfoControl().addTo(map);

const stageVisible = {
  has_final_price: true,
  start_price_only: true,
  no_price: true,
};

const renovationAreaLayer = L.layerGroup();
const filterFinalLayer = L.layerGroup();
const filterStartOnlyLayer = L.layerGroup();
const filterNoPriceLayer = L.layerGroup();

function lazyPopupHtml(group) {
  if (!group._popupHtml) {
    group._popupHtml = popupRenovationArea(group, group.tenders);
  }
  return group._popupHtml;
}

function bindLazyPopup(layer, group) {
  layer.bindPopup('<div class="small">Подготовка списка торгов...</div>');
  layer.on('popupopen', event => {
    const popup = event.popup;
    if (popup._renovationContentReady) return;
    popup.setContent(lazyPopupHtml(group));
    popup._renovationContentReady = true;
    popup.update();
  });
}

function addRenovationGroup(group) {
  const tenders = group.tenders;
  const latlng = [group.lat, group.lon];
  const color = colorByTenders(tenders);
  const circle = L.circle(latlng, {
    radius: Number(__RADIUS__),
    color,
    fillColor: color,
    fillOpacity: 0.12,
    opacity: 0.8,
    weight: 2,
  });
  const marker = L.marker(latlng, {
    icon: areaIcon(tenders.length, color),
  });

  // Большие HTML-списки торгов строятся только при открытии popup, а не для
  // всех точек во время старта страницы.
  bindLazyPopup(circle, group);
  bindLazyPopup(marker, group);
  renovationAreaLayer.addLayer(circle);
  renovationAreaLayer.addLayer(marker);
}

let renderGeneration = 0;
let renderFrame = null;

function setLoadingStatus(text, visible = true) {
  const el = window.mapLoadingStatusElement;
  if (!el) return;
  el.textContent = text;
  el.style.display = visible ? '' : 'none';
}

function rebuildRenovationAreasAndLinks(options = {}) {
  const generation = ++renderGeneration;
  if (renderFrame !== null) {
    cancelAnimationFrame(renderFrame);
    renderFrame = null;
  }

  renovationAreaLayer.clearLayers();
  const groups = groupVisibleTendersByRenovation();
  if (options.fitBounds) fitMapToRenovationGroups(groups);

  let index = 0;
  const total = groups.length;
  setLoadingStatus(`Добавление точек на карту: 0 из ${total}`);

  function renderBatch() {
    if (generation !== renderGeneration) return;

    const started = performance.now();
    let added = 0;
    while (index < total && added < 20 && performance.now() - started < 10) {
      const group = groups[index++];
      if (group.tenders.length > 0) addRenovationGroup(group);
      added += 1;
    }

    setLoadingStatus(`Добавление точек на карту: ${index} из ${total}`);
    if (index < total) {
      renderFrame = requestAnimationFrame(renderBatch);
      return;
    }

    renderFrame = null;
    setLoadingStatus(`Готово: ${total} точек`, true);
    window.setTimeout(() => {
      if (generation === renderGeneration) setLoadingStatus('', false);
    }, 900);
  }

  renderFrame = requestAnimationFrame(renderBatch);
  return groups;
}

function fitMapToRenovationGroups(groups) {
  const points = groups
    .filter(g => Number.isFinite(g.lat) && Number.isFinite(g.lon))
    .map(g => [g.lat, g.lon]);

  if (points.length > 0) {
    map.fitBounds(L.latLngBounds(points).pad(0.1));
  } else {
    map.setView([55.751244, 37.618423], 10);
  }
}



function formatMoneyInputValue(value) {
  const digits = String(value || '').replace(/\\D+/g, '');
  if (!digits) return '';
  return digits.replace(/\\B(?=(\\d{3})+(?!\\d))/g, ' ');
}

function parsePriceFilterInput(id) {
  const el = document.getElementById(id);
  if (!el) return null;
  const raw = String(el.value || '').replace(/\\D+/g, '');
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

let filterRefreshTimer = null;

function scheduleFilterRefresh(delay = 140) {
  if (filterRefreshTimer !== null) window.clearTimeout(filterRefreshTimer);
  filterRefreshTimer = window.setTimeout(() => {
    filterRefreshTimer = null;
    refreshByFilters();
  }, delay);
}

function attachPriceFilterInput(input) {
  input.addEventListener('input', () => {
    input.value = formatMoneyInputValue(input.value);
    scheduleFilterRefresh();
  });
  input.addEventListener('change', () => {
    input.value = formatMoneyInputValue(input.value);
    scheduleFilterRefresh(0);
  });
}

function readPriceFilters() {
  priceFilters.priceMin = parsePriceFilterInput('price-min');
  priceFilters.priceMax = parsePriceFilterInput('price-max');
  priceFilters.priceM2Min = parsePriceFilterInput('price-m2-min');
  priceFilters.priceM2Max = parsePriceFilterInput('price-m2-max');
}

function refreshByFilters() {
  readPriceFilters();
  updateYearFilterLabel();
  rebuildRenovationAreasAndLinks();
}

function createPriceFilterControl() {
  const control = L.control({ position: 'topright' });
  control.onAdd = function onAdd() {
    const div = L.DomUtil.create('div', 'map-panel fixed-map-panel price-filter-control');
    div.innerHTML = [
      '<div class="price-filter-title">Фильтры</div>',
      '<label>Год</label>',
      '<select id="year-filter"></select>',
      '<label>Цена, руб.</label>',
      '<div class="price-filter-row">',
      '<input id="price-min" type="text" inputmode="numeric" placeholder="от">',
      '<input id="price-max" type="text" inputmode="numeric" placeholder="до">',
      '</div>',
      '<label>Цена за m2, руб.</label>',
      '<div class="price-filter-row">',
      '<input id="price-m2-min" type="text" inputmode="numeric" placeholder="от">',
      '<input id="price-m2-max" type="text" inputmode="numeric" placeholder="до">',
      '</div>',
      '<div class="small" style="margin-top:6px;">',
      'Берется итоговая цена, если есть, иначе начальная.',
      '</div>',
      '<button id="price-filter-reset" type="button">Сброс</button>',
    ].join('');

    L.DomEvent.disableClickPropagation(div);
    L.DomEvent.disableScrollPropagation(div);

    const yearSelect = div.querySelector('#year-filter');
    fillYearFilterSelect(yearSelect);
    yearSelect.addEventListener('change', () => {
      selectedYear = parseYearFilterValue(yearSelect.value);
      refreshByFilters();
    });

    for (const input of div.querySelectorAll('input')) {
      attachPriceFilterInput(input);
    }

    const reset = div.querySelector('#price-filter-reset');
    reset.addEventListener('click', () => {
      for (const input of div.querySelectorAll('input')) input.value = '';
      yearSelect.value = defaultYearFilterValue(availableYears());
      selectedYear = parseYearFilterValue(yearSelect.value);
      refreshByFilters();
    });

    return div;
  };
  return control;
}

const overlayMaps = {
  'Окрестности реновации': renovationAreaLayer,
  'Фильтр: есть итоговая цена': filterFinalLayer,
  'Фильтр: только начальная цена': filterStartOnlyLayer,
  'Фильтр: без цены': filterNoPriceLayer,
};

renovationAreaLayer.addTo(map);
filterFinalLayer.addTo(map);
filterStartOnlyLayer.addTo(map);
filterNoPriceLayer.addTo(map);

const filterNameToStage = {
  'Фильтр: есть итоговая цена': 'has_final_price',
  'Фильтр: только начальная цена': 'start_price_only',
  'Фильтр: без цены': 'no_price',
};

map.on('overlayadd overlayremove', e => {
  const stage = filterNameToStage[e.name];
  if (!stage) return;
  stageVisible[stage] = e.type === 'overlayadd';
  rebuildRenovationAreasAndLinks();
});

function initializeApplication() {
  setLoadingStatus('Чтение данных торгов...');

  // JSON.parse и группировку запускаем после первого кадра. Карта и индикатор
  // к этому моменту уже нарисованы.
  requestAnimationFrame(() => {
    window.setTimeout(() => {
      try {
        const dataElement = document.getElementById('tender-data');
        tenderData = JSON.parse(dataElement ? dataElement.textContent : '[]');

        createPriceFilterControl().addTo(map);
        requestAnimationFrame(syncTopPanelHeights);

        const layersControl = L.control.layers(
          null,
          overlayMaps,
          { collapsed: false, position: 'topright' },
        ).addTo(map);
        L.DomUtil.addClass(layersControl.getContainer(), 'map-panel');
        L.DomUtil.addClass(layersControl.getContainer(), 'fixed-map-panel');

        rebuildRenovationAreasAndLinks({ fitBounds: true });
      } catch (error) {
        console.error(error);
        setLoadingStatus(`Ошибка загрузки: ${error.message || error}`);
      }
    }, 0);
  });
}

initializeApplication();
</script>
</body>
</html>
"""
    return template.replace("__TENDERS_JSON__", tenders_json).replace(
        "__RADIUS__", radius_s
    )


def year_filter_text(args):
    parts = []
    if args.year:
        parts.append("год " + ",".join(str(y) for y in sorted(set(args.year))))
    if args.year_from is not None:
        parts.append(f"с {args.year_from}")
    if args.year_to is not None:
        parts.append(f"по {args.year_to}")
    if not parts:
        return "нет"
    if args.include_unknown_year:
        parts.append("+ без года")
    return " ".join(parts)


def main():
    args = parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    renovation_points = load_coords(args.coords)
    files = sorted(p for p in Path(args.data_dir).glob("*.json") if p.is_file())

    matches = []
    skipped = defaultdict(int)

    for p in files:
        try:
            obj = load_json(p)
            if not obj:
                skipped["empty_json"] += 1
                continue

            c = obj.get("mapInfo", {}).get("coords", {})
            lat = c.get("lat")
            lon = c.get("long")
            if lat is None or lon is None:
                skipped["no_coords"] += 1
                continue
            lat = float(lat)
            lon = float(lon)

            labels = build_label_map(obj)
            (
                year,
                applications_start_date,
                applications_end_date,
                year_source_label,
            ) = extract_year_and_dates(labels)
            if not year_passes(year, args):
                skipped["year_filter"] += 1
                continue

            rp, dist_m = nearest_renovation(lat, lon, renovation_points)
            if rp is None or dist_m is None or dist_m > args.radius:
                skipped["outside_radius"] += 1
                continue

            status = (
                obj.get("sidebar", {})
                .get("tenderStatusInfo", {})
                .get("statusText", "")
                .strip()
            )
            tender_id = obj.get("tenderId") or p.stem
            start = extract_start_price(obj, labels)
            final = extract_final_price(labels)
            area = extract_area(labels)

            ratio = (
                (final / start) if (final is not None and start and start > 0) else None
            )
            delta_pct = ((ratio - 1.0) * 100.0) if ratio is not None else None
            delta_rub = (
                (final - start) if (final is not None and start is not None) else None
            )
            price_m2_start = (start / area) if (area and start is not None) else None
            price_m2_final = (final / area) if (area and final is not None) else None
            stage = price_stage(start, final)

            matches.append(
                {
                    "tenderId": tender_id,
                    "status": status,
                    "year": year,
                    "year_source_label": year_source_label,
                    "address": extract_address(labels),
                    "area_m2": area,
                    "start_price": start,
                    "final_price": final,
                    "delta_rub": delta_rub,
                    "ratio": ratio,
                    "delta_pct": delta_pct,
                    "price_m2_start": price_m2_start,
                    "price_m2_final": price_m2_final,
                    "price_stage": stage,
                    "applications_start_date": applications_start_date,
                    "applications_end_date": applications_end_date,
                    "tender_lat": lat,
                    "tender_lon": lon,
                    "renovation_id": rp["renovation_id"],
                    "renovation_lat": rp["lat"],
                    "renovation_lon": rp["lon"],
                    "dist_m": dist_m,
                    "source_file": p.name,
                    "tender_url": f"https://investmoscow.ru/tenders/tender/{tender_id}",
                }
            )
        except Exception:
            skipped["exceptions"] += 1
            continue

    by_reno = defaultdict(list)
    for r in matches:
        by_reno[r["renovation_id"]].append(r)

    if args.include_empty_renovation_points:
        source_points = renovation_points
    else:
        source_points = [
            rp for rp in renovation_points if rp["renovation_id"] in by_reno
        ]
    summary_rows = []
    for rp in source_points:
        rs = by_reno.get(rp["renovation_id"], [])
        with_final = [r for r in rs if r["final_price"] is not None]
        start_only = [r for r in rs if r["price_stage"] == "start_price_only"]
        deltas = [r["delta_pct"] for r in with_final]
        summary_rows.append(
            {
                "renovation_id": rp["renovation_id"],
                "renovation_lat": rp["lat"],
                "renovation_lon": rp["lon"],
                "tenders_count": len(rs),
                "with_final_price_count": len(with_final),
                "start_price_only_count": len(start_only),
                "no_price_count": sum(1 for r in rs if r["price_stage"] == "no_price"),
                "avg_delta_pct": avg_or_none(deltas),
                "median_delta_pct": median_or_none(deltas),
            }
        )

    tender_features = []
    for r in matches:
        props = {
            k: v
            for k, v in r.items()
            if k
            not in (
                "tender_lat",
                "tender_lon",
            )
        }
        tender_features.append(feature_point(r["tender_lon"], r["tender_lat"], props))

    tenders_fc = fc(tender_features)
    summary_fc = fc(
        [
            feature_point(
                r["renovation_lon"],
                r["renovation_lat"],
                {
                    k: v
                    for k, v in r.items()
                    if k not in ("renovation_lat", "renovation_lon")
                },
            )
            for r in summary_rows
        ]
    )

    html_map_path = out_dir / "renovation_map.html"
    html_map_path.write_text(
        build_map_html(
            summary_fc,
            tenders_fc,
            args.radius,
            year_filter_text(args),
        ),
        encoding="utf-8",
    )

    price_stage_counts = defaultdict(int)
    years = defaultdict(int)
    for r in matches:
        price_stage_counts[r["price_stage"]] += 1
        years[str(r["year"] or "unknown")] += 1

    print(
        f"matched_tenders={len(matches)} "
        f"radius_m={args.radius:g} "
        f"year_filter={year_filter_text(args)}"
    )
    for k in sorted(price_stage_counts):
        print(f"matched_{k}={price_stage_counts[k]}")
    for y in sorted(years):
        print(f"year_{y}={years[y]}")
    print(f"renovation_points_with_matches={len(by_reno)}")
    for k in sorted(skipped):
        print(f"skipped_{k}={skipped[k]}")
    print(f"wrote: {html_map_path}")


if __name__ == "__main__":
    main()
