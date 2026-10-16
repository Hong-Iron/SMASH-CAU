# Downloads the campus outline, nearby OpenStreetMap features and elevation tiles.
# usage: python3 tools/fetch.py <way|relation> <osm_id> <raw_dir> [margin_m]
import json, math, os, subprocess, sys, time, urllib.parse, urllib.request

OTYPE, OID, RAW = sys.argv[1], sys.argv[2], sys.argv[3]
MARGIN = float(sys.argv[4]) if len(sys.argv) > 4 else 45.0
MIRRORS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter",
           "https://maps.mail.ru/osm/tools/overpass/api/interpreter", "https://overpass.kumi.systems/api/interpreter"]
UA = {"User-Agent": "SMASH campus data build (github.com/Hong-Iron)"}

def http(url, data=None):
    # urllib first; curl as a fallback (some Python installs on macOS lack CA certificates)
    try:
        req = urllib.request.Request(url, data=data, headers=UA)
        with urllib.request.urlopen(req, timeout=200) as r:
            return r.read()
    except Exception:
        cmd = ["curl", "-sf", "-m", "200", "-A", UA["User-Agent"], url]
        if data is not None: cmd += ["--data-binary", "@-"]
        return subprocess.run(cmd, input=data, capture_output=True, check=True).stdout

def overpass(q):
    body = urllib.parse.urlencode({"data": q}).encode()
    for attempt in range(3):
        for url in MIRRORS:
            try:
                data = http(url, body)
                if data[:1] == b"{":
                    return json.loads(data)
            except Exception as e:
                print("  retry:", url, type(e).__name__)
        time.sleep(5)
    raise SystemExit("Overpass failed")

os.makedirs(os.path.join(RAW, "dem"), exist_ok=True)
campus = overpass(f"[out:json][timeout:90];{OTYPE}({OID});out geom;")
json.dump(campus, open(os.path.join(RAW, "campus.json"), "w"))
el = campus["elements"][0]
pts = el["geometry"] if el["type"] == "way" else [p for m in el["members"] if m.get("role") == "outer" for p in m.get("geometry", [])]
lats = [p["lat"] for p in pts]; lons = [p["lon"] for p in pts]
lat0 = (min(lats) + max(lats)) / 2; lon0 = (min(lons) + max(lons)) / 2
dlat = MARGIN / 110987; dlon = MARGIN / (111320 * math.cos(math.radians(lat0)))
S_, W_, N_, E_ = min(lats) - dlat, min(lons) - dlon, max(lats) + dlat, max(lons) + dlon
bb = f"{S_:.7f},{W_:.7f},{N_:.7f},{E_:.7f}"
area = overpass(f'[out:json][timeout:180];(way["building"]({bb});relation["building"]({bb});way["highway"]({bb});'
                f'way["landuse"]({bb});way["leisure"]({bb});way["natural"]({bb});relation["natural"]({bb});relation["landuse"]({bb}););out geom;')
json.dump(area, open(os.path.join(RAW, "area.json"), "w"))

Z = 15
def tile(lat, lon):
    n = 2 ** Z
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
x0, y0 = tile(N_, W_); x1, y1 = tile(S_, E_)
for x in range(x0, x1 + 1):
    for y in range(y0, y1 + 1):
        dst = os.path.join(RAW, "dem", f"{Z}_{x}_{y}.png")
        if not os.path.exists(dst):
            open(dst, "wb").write(http(f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{x}/{y}.png"))
json.dump({"otype": OTYPE, "oid": OID, "bbox": [S_, W_, N_, E_], "center": [lat0, lon0], "margin": MARGIN}, open(os.path.join(RAW, "meta.json"), "w"))
print(f"saved: {len(area['elements'])} features, {(x1-x0+1)*(y1-y0+1)} elevation tiles, bbox {bb}")
