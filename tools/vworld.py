# Buildings, floors and roof colours from 국토교통부 디지털트윈국토(브이월드), 공공누리 제1유형(출처표시).
# usage: python3 tools/vworld.py [--refresh]          (numpy, matplotlib, Pillow; key VWORLD_KEY in .env, never committed)
#   1. 연속지적도(LP_PA_CBND_BUBUN): parcels whose land category is 학(school site) and that touch the campus are the school
#   2. 건물통합정보(LT_C_BLDGINFO): buildings standing on those parcels (or inside the OSM campus) give floors, height and
#      dong names to the OSM buildings they overlap; school buildings OpenStreetMap lacks are added
#   3. 항공영상(Satellite WMTS, zoom 18): each roof's median colour is stored as "rc"
# Downloads are cached in raw/vworld/ (git-ignored). On campuses fetched as a circle, buildings named as homes or other
# schools (아파트, 초·중·고등학교, 유치원 …) are left out; the school-site parcels alone missed real halls on 대 land.
import io, json, math, os, pathlib, re, subprocess, sys, urllib.parse
import numpy as np
from matplotlib.path import Path
from PIL import Image

root = pathlib.Path(__file__).resolve().parent.parent
cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
camp_p = root / "data" / "campus.json"
cache = root / "raw" / "vworld"; cache.mkdir(parents=True, exist_ok=True)
REFRESH = "--refresh" in sys.argv
DOMAIN = "https://hong-iron.github.io"


def key():
    env = root / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("VWORLD_KEY="): return line.split("=", 1)[1].strip()
    if os.environ.get("VWORLD_KEY"): return os.environ["VWORLD_KEY"]
    sys.exit("VWORLD_KEY is missing: put it in .env (git-ignored)")


def get(url):
    # python.org builds on macOS ship without CA certificates, so curl does the transfer
    r = subprocess.run(["curl", "-s", "--max-time", "60", "--retry", "3", url], capture_output=True, check=True)
    return r.stdout


def features(layer, box):
    f = cache / f"{layer}.json"
    if f.exists() and not REFRESH: return json.loads(f.read_text(encoding="utf-8"))
    out, page, k = [], 1, key()
    while True:
        q = dict(service="data", request="GetFeature", data=layer, key=k, domain=DOMAIN, format="json", crs="EPSG:4326",
                 geometry="true", attribute="true", size=1000, page=page, geomFilter="BOX(%.6f,%.6f,%.6f,%.6f)" % box)
        r = json.loads(get("https://api.vworld.kr/req/data?" + urllib.parse.urlencode(q)))["response"]
        if r["status"] == "NOT_FOUND": break
        if r["status"] != "OK": sys.exit(f"{layer}: {r.get('error')}")
        out += r["result"]["featureCollection"]["features"]
        if page >= int(r["page"]["total"]): break
        page += 1
    f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


data = json.loads(camp_p.read_text(encoding="utf-8"))
LAT0, LON0 = data["meta"]["lat"], data["meta"]["lon"]
phi = math.radians(LAT0)
MLAT = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
MLON = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
xz = lambda lon, lat: (round((lon - LON0) * MLON, 1), round((LAT0 - lat) * MLAT, 1))
T = data["terrain"]; dm = np.array(T["dm"], dtype=float).reshape(T["nz"], T["nx"]) / 10


def ground(x, z):
    j = min(max((x - T["x0"]) / T["step"], 0), T["nx"] - 1.001); i = min(max((z - T["z0"]) / T["step"], 0), T["nz"] - 1.001)
    j0, i0 = int(j), int(i); fx, fz = j - j0, i - i0; v = dm[i0:i0 + 2, j0:j0 + 2]
    return float(v[0, 0] * (1 - fx) * (1 - fz) + v[0, 1] * fx * (1 - fz) + v[1, 0] * (1 - fx) * fz + v[1, 1] * fx * fz)


def area(r): return abs(sum(r[i][0] * r[i - 1][1] - r[i - 1][0] * r[i][1] for i in range(len(r)))) / 2
def centroid(r): return (sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r))
def rings(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    out = []
    for poly in polys:
        outer = [xz(lon, lat) for lon, lat in poly[0]]
        if len(outer) > 1 and outer[0] == outer[-1]: outer = outer[:-1]
        if len(outer) >= 3: out.append(outer)
    return out


def overlap(a, b, n=16):
    # area of a ∩ b estimated on an n×n grid over their common box
    ax, az = zip(*a); bx, bz = zip(*b)
    x0, x1, z0, z1 = max(min(ax), min(bx)), min(max(ax), max(bx)), max(min(az), min(bz)), min(max(az), max(bz))
    if x0 >= x1 or z0 >= z1: return 0.0
    g = np.stack(np.meshgrid(np.linspace(x0, x1, n, endpoint=False) + (x1 - x0) / (2 * n),
                             np.linspace(z0, z1, n, endpoint=False) + (z1 - z0) / (2 * n)), -1).reshape(-1, 2)
    hit = Path(a).contains_points(g) & Path(b).contains_points(g)
    return (x1 - x0) * (z1 - z0) * hit.mean()


# ---- area to fetch: campus, buildings and a margin, back to lon/lat
pts = [p for r in data["campus"] for p in r] + [p for b in data["buildings"] for p in b["o"]]
X0, X1 = min(p[0] for p in pts) - 40, max(p[0] for p in pts) + 40
Z0, Z1 = min(p[1] for p in pts) - 40, max(p[1] for p in pts) + 40
box = (LON0 + X0 / MLON, LAT0 - Z1 / MLAT, LON0 + X1 / MLON, LAT0 - Z0 / MLAT)

# ---- 1. school parcels
circle = (cfg.get("osm") or {}).get("type") == "circle"
camp_paths = [Path(r) for r in data["campus"]]
def in_campus(p): return any(cp.contains_point(p) for cp in camp_paths)
parcels = []
for f in features("LP_PA_CBND_BUBUN", box):
    j = f["properties"].get("jibun") or ""
    if not j.endswith("학"): continue
    for r in rings(f["geometry"]):
        if area(r) < 30: continue
        c = centroid(r)
        inside = in_campus(c) or any(in_campus(p) for p in r[:: max(1, len(r) // 12)])
        if inside: parcels.append(dict(pnu=f["properties"]["pnu"], ring=r))
par_paths = [Path(p["ring"]) for p in parcels]
def on_school(p): return any(pp.contains_point(p) for pp in par_paths)
print(f"school parcels (지목 학) touching the campus: {len(parcels)}")

# ---- 2. buildings
GENERIC = {cfg.get("fullName", ""), cfg.get("school", ""), cfg.get("campusName", "")}
NOT_CAMPUS = re.compile(r"아파트|빌라|빌리지아파트|맨션|주택|초등학교|중학교|고등학교|여중|여고|유치원|어린이집|교회|성당")
vw = []
for f in features("LT_C_BLDGINFO", box):
    p = f["properties"]
    for r in rings(f["geometry"]):
        a = area(r)
        if a < 40: continue
        c = centroid(r)
        if not (on_school(c) or (not circle and in_campus(c))): continue
        lv = int(float(p.get("grnd_flr") or 0)); h = float(p.get("height") or 0)
        name = (p.get("dong_nm") or "").strip() or (p.get("bld_nm") or "").strip()
        if circle and NOT_CAMPUS.search((p.get("bld_nm") or "") + " " + (p.get("dong_nm") or "")): continue
        if name in GENERIC or name.startswith(cfg.get("fullName", "~")) and len(name) <= len(cfg.get("fullName", "")) + 1: name = ""
        vw.append(dict(ring=r, area=a, c=c, lv=lv, h=h, name=name, use=p.get("usability")))
print(f"school buildings in 건물통합정보: {len(vw)}")

bs = data["buildings"]
for b in bs: b["_a"] = area(b["o"])
upd = named = 0
for b in bs:
    best, bo = None, 0.0
    for v in vw:
        if abs(v["c"][0] - centroid(b["o"])[0]) > 300 or abs(v["c"][1] - centroid(b["o"])[1]) > 300: continue
        o = overlap(b["o"], v["ring"])
        if o > bo: best, bo = v, o
    if best and bo >= 0.4 * min(b["_a"], best["area"]):
        best["used"] = True
        if best["lv"] > 0:
            h = best["h"] if best["h"] >= best["lv"] * 2.4 else best["lv"] * 4.0
            if b.get("lv") != best["lv"] or abs(b["h"] - h) > 0.5:
                b["lv"], b["h"] = best["lv"], round(h, 1); upd += 1
        if not b.get("n") and best["name"]: b["n"] = best["name"]; named += 1
        for v in vw:
            if v is not best and not v.get("used") and overlap(b["o"], v["ring"]) >= 0.5 * v["area"]: v["used"] = True
dropped = 0
if circle:
    keep = []
    for b in bs:
        if b.get("n") and NOT_CAMPUS.search(b["n"]): dropped += 1
        else: keep.append(b)
    data["buildings"] = bs = keep
added = 0
for i, v in enumerate(vw):
    if v.get("used"): continue
    if any(overlap(b["o"], v["ring"]) > 0.25 * v["area"] for b in bs): continue
    lv = v["lv"] if v["lv"] > 0 else None
    # floors unknown: a small footprint is a shed or guard post, a large one a hall
    guess = 1 if v["area"] < 150 else 2 if v["area"] < 400 else 4
    h = v["h"] if (lv and v["h"] >= lv * 2.4) else (lv or guess) * 4.0
    samples = [ground(x, z) for x, z in v["ring"]] + [ground(*v["c"])]
    bs.append(dict(id=f"vw/{i}", n=v["name"] or None, campus=True, kind="university", lv=lv, h=round(h, 1),
                   g=round(sum(samples) / len(samples), 1), lo=round(min(samples), 1), o=[list(p) for p in v["ring"]], ho=[]))
    added += 1
for b in bs: b.pop("_a", None)
# trees standing inside a new footprint go
new_paths = [Path(b["o"]) for b in bs if str(b["id"]).startswith("vw/")]
if new_paths:
    data["trees"] = [t for t in data["trees"] if not any(pp.contains_point((t[0], t[1])) for pp in new_paths)]
print(f"floors/height from 건물통합정보: {upd}, names filled: {named}, added: {added}, dropped homes/other schools (circle): {dropped}")

# ---- 3. roof colours from aerial imagery
Z = 18
def tile_xy(lon, lat):
    n = 2 ** Z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
tx0, ty0 = tile_xy(box[0], box[3]); tx1, ty1 = tile_xy(box[2], box[1])
tx0, ty0, tx1, ty1 = int(tx0), int(ty0), int(tx1), int(ty1)
mos = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
k = None
for ty in range(ty0, ty1 + 1):
    for tx in range(tx0, tx1 + 1):
        f = cache / f"sat_{Z}_{ty}_{tx}.jpg"
        if not f.exists() or REFRESH:
            k = k or key()
            f.write_bytes(get(f"https://api.vworld.kr/req/wmts/1.0.0/{k}/Satellite/{Z}/{ty}/{tx}.jpeg"))
        try: mos.paste(Image.open(f).convert("RGB"), ((tx - tx0) * 256, (ty - ty0) * 256))
        except Exception: pass
img = np.asarray(mos).astype(float)
def px(x, z):
    tx, ty = tile_xy(LON0 + x / MLON, LAT0 - z / MLAT)
    return (tx - tx0) * 256, (ty - ty0) * 256
colored = 0
for b in bs:
    cx, cz = centroid(b["o"])
    ring = [(cx + (x - cx) * 0.8, cz + (z - cz) * 0.8) for x, z in b["o"]]   # stay off the eaves and wall shadows
    pr = [px(x, z) for x, z in ring]
    us, vs = zip(*pr)
    u0, u1, v0, v1 = int(max(0, min(us))), int(min(img.shape[1] - 1, max(us))), int(max(0, min(vs))), int(min(img.shape[0] - 1, max(vs)))
    if u1 - u0 < 2 or v1 - v0 < 2: continue
    gu, gv = np.meshgrid(np.arange(u0, u1 + 1), np.arange(v0, v1 + 1))
    m = Path(pr).contains_points(np.stack([gu.ravel() + 0.5, gv.ravel() + 0.5], -1))
    if m.sum() < 12: continue
    c = img[gv.ravel()[m], gu.ravel()[m]]
    lum = c @ [0.299, 0.587, 0.114]
    lo, hi = np.percentile(lum, 30), np.percentile(lum, 95)   # drop shade from parapets and rooftop units
    c = c[(lum >= lo) & (lum <= hi)]
    if not len(c): continue
    r, g, bl = np.median(c, axis=0)
    if g > r + 6 and g >= bl and (r + g + bl) / 3 < 92: continue   # tree canopy over the roof, not the roof itself
    b["rc"] = "#%02x%02x%02x" % tuple(int(min(255, v * 1.08)) for v in (r, g, bl))
    colored += 1
print(f"roof colours from aerial imagery: {colored} / {len(bs)}")
camp_p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
