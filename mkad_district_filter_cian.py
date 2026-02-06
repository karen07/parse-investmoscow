#!/usr/bin/python3

import sys
import json
from pathlib import Path
from urllib.parse import quote

from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.ops import transform
from pyproj import Transformer

DEFAULT_OUT = "districts_in_mkad.geojson"

MIN_RATIO = 0.1  # keep if >= this fraction inside MKAD
SIMPLIFY_M = 60.0  # simplify in meters in EPSG:3857; 0 disables
MKAD_BUFFER_M = 0.0  # buffer MKAD in meters; 0 disables

DROP_PROPERTIES = 1  # 1: drop properties, 0: keep
PRINT_URLS = 1  # 1: print CIAN URLs, 0: no output


def die(msg):
    print("error:", msg, file=sys.stderr)
    sys.exit(2)


def usage():
    print(
        "usage:\n"
        "  mkad_filter.py <districts.geojson> <mkad.geojson> [out.geojson] [--clip]\n",
        file=sys.stderr,
    )
    sys.exit(2)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_geom_any(path):
    obj = load_json(path)
    t = obj.get("type")
    if t == "FeatureCollection":
        feats = obj.get("features") or []
        if not feats:
            die(f"{path}: empty FeatureCollection")
        return shape(feats[0]["geometry"])
    if t == "Feature":
        return shape(obj["geometry"])
    return shape(obj)


def project_4326_to_3857(geom):
    tr = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    return transform(tr.transform, geom)


def project_3857_to_4326(geom):
    tr = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    return transform(tr.transform, geom)


def get_name_from_properties(props):
    if not isinstance(props, dict):
        return None

    v = props.get("name")
    if isinstance(v, str) and v.strip():
        return v.strip()

    tags = props.get("tags")
    if isinstance(tags, dict):
        for k in ("name:en", "name"):
            v = tags.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    return None


def pick_main_ring_wgs84(geom_wgs84):
    if isinstance(geom_wgs84, Polygon):
        poly = geom_wgs84
    elif isinstance(geom_wgs84, MultiPolygon):
        polys = list(geom_wgs84.geoms)
        if not polys:
            return None
        poly = max(polys, key=lambda p: p.area)
    else:
        try:
            acc = []
            for g in getattr(geom_wgs84, "geoms", []):
                if isinstance(g, Polygon):
                    acc.append(g)
                elif isinstance(g, MultiPolygon):
                    acc.extend(list(g.geoms))
            if not acc:
                return None
            poly = max(acc, key=lambda p: p.area)
        except Exception:
            return None

    coords = list(poly.exterior.coords)
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def build_cian_url(polygon_coords_lonlat, center_lat, center_lon):
    raw_pairs = ",".join(
        [f"{lon:.6f}_{lat:.6f}" for (lon, lat) in polygon_coords_lonlat]
    )
    in_polygon = quote(raw_pairs, safe="._-")
    center = quote(f"{center_lat:.6f},{center_lon:.6f}", safe="")

    base = (
        "https://www.cian.ru/cat.php?"
        "currency=2&deal_type=sale&engine_version=2&flat_share=2&"
        "minkarea=8&mintarea=34&object_type[0]=1&offer_type=flat&"
        "only_flat=1&polygon_name[0]=default_name_0&wp=1&zoom=10"
    )

    return f"{base}&center={center}&in_polygon[0]={in_polygon}"


def parse_args(argv):
    clip = 0
    pos = []

    for a in argv[1:]:
        if a == "--clip":
            clip = 1
        elif a.startswith("-"):
            usage()
        else:
            pos.append(a)

    if len(pos) < 2 or len(pos) > 3:
        usage()

    districts = pos[0]
    mkad = pos[1]
    out = pos[2] if len(pos) == 3 else DEFAULT_OUT

    return districts, mkad, out, clip


def main(argv):
    districts_path, mkad_path, out_path, clip = parse_args(argv)

    mkad_wgs84 = load_geom_any(mkad_path)
    mkad = project_4326_to_3857(mkad_wgs84)
    if MKAD_BUFFER_M != 0.0:
        mkad = mkad.buffer(MKAD_BUFFER_M)

    data = load_json(districts_path)
    feats = data.get("features") or []

    kept = []
    kept_for_urls = []

    idx = 0
    for f in feats:
        idx += 1

        props_src = f.get("properties") or {}
        name = get_name_from_properties(props_src) or f"district_{idx}"

        geom_wgs84 = shape(f["geometry"])
        geom_p = project_4326_to_3857(geom_wgs84)

        if geom_p.is_empty or geom_p.area <= 0:
            continue

        inter_p = geom_p.intersection(mkad)
        ratio = (inter_p.area / geom_p.area) if geom_p.area else 0.0
        rep_inside = mkad.contains(geom_p.representative_point())

        if ratio < MIN_RATIO and not rep_inside:
            continue

        geom_used_p = inter_p if clip else geom_p

        if SIMPLIFY_M > 0.0:
            geom_used_p = geom_used_p.simplify(SIMPLIFY_M, preserve_topology=True)

        kept_for_urls.append((name, geom_used_p))

        if clip:
            out_geom = mapping(project_3857_to_4326(inter_p))
        else:
            out_geom = f["geometry"]

        kept.append(
            {
                "type": "Feature",
                "properties": {} if DROP_PROPERTIES else dict(props_src),
                "geometry": out_geom,
            }
        )

    out = {"type": "FeatureCollection", "features": kept}
    Path(out_path).write_text(json.dumps(out, ensure_ascii=True), encoding="utf-8")

    print("Input :", len(feats))
    print("Kept  :", len(kept))
    print("Saved :", out_path)

    if PRINT_URLS:
        out_urls = []
        for name, geom_p in kept_for_urls:
            geom_wgs84 = project_3857_to_4326(geom_p)
            ring = pick_main_ring_wgs84(geom_wgs84)
            if not ring or len(ring) < 4:
                continue

            rp = geom_wgs84.representative_point()
            center_lon, center_lat = rp.x, rp.y

            url = build_cian_url(ring, center_lat, center_lon)
            out_urls.append(f"{name} : {url}\n")

        Path("cian.txt").write_text("".join(out_urls), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
