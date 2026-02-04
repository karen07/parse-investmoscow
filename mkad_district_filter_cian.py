import json
import argparse
from pathlib import Path
from urllib.parse import quote

from shapely.geometry import shape, mapping, Polygon, MultiPolygon
from shapely.ops import transform
from pyproj import Transformer


def load_geom_any(path: str):
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    t = obj.get("type")
    if t == "FeatureCollection":
        return shape(obj["features"][0]["geometry"])
    if t == "Feature":
        return shape(obj["geometry"])
    return shape(obj)


def project_4326_to_3857(geom):
    tr = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
    return transform(tr.transform, geom)


def project_3857_to_4326(geom):
    tr = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)
    return transform(tr.transform, geom)


def get_name_from_properties(props: dict) -> str | None:
    if not isinstance(props, dict):
        return None

    if isinstance(props.get("name"), str) and props["name"].strip():
        return props["name"].strip()

    tags = props.get("tags")
    if isinstance(tags, dict):
        for k in ("name:en", "name"):
            v = tags.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    return None


def pick_main_ring_wgs84(geom_wgs84):
    """
    Return exterior ring coordinates (lon, lat).
    For MultiPolygon, choose the largest polygon.
    """
    if isinstance(geom_wgs84, Polygon):
        poly = geom_wgs84
    elif isinstance(geom_wgs84, MultiPolygon):
        polys = list(geom_wgs84.geoms)
        if not polys:
            return None
        poly = max(polys, key=lambda p: p.area)
    else:
        try:
            polys = [g for g in geom_wgs84.geoms if isinstance(g, (Polygon, MultiPolygon))]
            if not polys:
                return None

            only_polys = []
            for g in polys:
                if isinstance(g, Polygon):
                    only_polys.append(g)
                elif isinstance(g, MultiPolygon):
                    only_polys.extend(list(g.geoms))

            if not only_polys:
                return None

            return pick_main_ring_wgs84(MultiPolygon(only_polys))
        except Exception:
            return None

    coords = list(poly.exterior.coords)
    if coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def build_cian_url(polygon_coords_lonlat, center_lat, center_lon, *, zoom=10, maxprice=12000000):
    raw_pairs = ",".join([f"{lon:.6f}_{lat:.6f}" for (lon, lat) in polygon_coords_lonlat])
    in_polygon = quote(raw_pairs, safe="._-")
    center = quote(f"{center_lat:.6f},{center_lon:.6f}", safe="")

    base = (
        "https://www.cian.ru/cat.php?"
        "currency=2&deal_type=sale&engine_version=2&flat_share=2"
        "&is_first_floor=0&minlift=1&mintarea=34&minkarea=7"
        f"&maxprice={int(maxprice)}"
        "&object_type[0]=1&offer_type=flat&only_flat=1"
        "&wp=1"
        f"&zoom={int(zoom)}"
        "&origin=map"
    )

    return f"{base}&center={center}&in_polygon[0]={in_polygon}"


def main():
    ap = argparse.ArgumentParser(
        description="Keep districts mostly inside MKAD and print CIAN URLs."
    )

    ap.add_argument("--districts", required=True, help="Districts GeoJSON")
    ap.add_argument("--mkad", required=True, help="MKAD polygon GeoJSON")
    ap.add_argument("--out", default="districts_in_mkad.geojson")

    ap.add_argument("--min-ratio", type=float, default=0.85)
    ap.add_argument("--mkad-buffer-m", type=float, default=0.0)
    ap.add_argument("--clip", action="store_true")

    ap.add_argument("--drop-properties", action="store_true", default=True)
    ap.add_argument("--keep-properties", dest="drop_properties", action="store_false")

    ap.add_argument("--print-urls", action="store_true", default=True)
    ap.add_argument("--no-print-urls", dest="print_urls", action="store_false")

    ap.add_argument("--simplify-m", type=float, default=60.0)
    ap.add_argument("--zoom", type=int, default=10)
    ap.add_argument("--maxprice", type=int, default=12000000)

    args = ap.parse_args()

    mkad_wgs84 = load_geom_any(args.mkad)
    mkad = project_4326_to_3857(mkad_wgs84)
    if args.mkad_buffer_m != 0:
        mkad = mkad.buffer(args.mkad_buffer_m)

    data = json.loads(Path(args.districts).read_text(encoding="utf-8"))
    feats = data.get("features", [])

    kept = []
    kept_for_urls = []

    for idx, f in enumerate(feats, start=1):
        props_src = f.get("properties", {}) or {}
        name = get_name_from_properties(props_src) or f"district_{idx}"

        geom_wgs84 = shape(f["geometry"])
        geom_p = project_4326_to_3857(geom_wgs84)

        if geom_p.is_empty or geom_p.area <= 0:
            continue

        inter_p = geom_p.intersection(mkad)
        ratio = (inter_p.area / geom_p.area) if geom_p.area else 0.0
        rep_inside = mkad.contains(geom_p.representative_point())

        if ratio >= args.min_ratio or rep_inside:
            geom_used_p = inter_p if args.clip else geom_p

            if args.simplify_m and args.simplify_m > 0:
                geom_used_p = geom_used_p.simplify(
                    args.simplify_m, preserve_topology=True
                )

            kept_for_urls.append((name, geom_used_p))

            if args.clip:
                out_geom = mapping(project_3857_to_4326(inter_p))
            else:
                out_geom = f["geometry"]

            kept.append({
                "type": "Feature",
                "properties": {} if args.drop_properties else dict(props_src),
                "geometry": out_geom,
            })

    out = {"type": "FeatureCollection", "features": kept}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=True), encoding="utf-8")

    print("Input :", len(feats))
    print("Kept  :", len(kept))
    print("Saved :", args.out)

    if args.print_urls:
        print("\nCIAN URLs:")
        for name, geom_p in kept_for_urls:
            geom_wgs84 = project_3857_to_4326(geom_p)
            ring = pick_main_ring_wgs84(geom_wgs84)
            if not ring or len(ring) < 4:
                continue

            rp = geom_wgs84.representative_point()
            center_lon, center_lat = rp.x, rp.y

            url = build_cian_url(
                ring,
                center_lat=center_lat,
                center_lon=center_lon,
                zoom=args.zoom,
                maxprice=args.maxprice,
            )

            print(f"{name} : {url}")


if __name__ == "__main__":
    main()
