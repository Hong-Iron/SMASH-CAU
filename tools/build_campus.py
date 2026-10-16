# Converts the raw downloads from tools/fetch.py into the game's local-metre JSON.
# usage: python3 tools/build_campus.py <raw_dir> <out.json> [grid_step_m]   (needs numpy and matplotlib)
import glob, json, math, os, sys
import numpy as np
import matplotlib.image as mimg

RAW, OUT = sys.argv[1], sys.argv[2]
meta = json.load(open(os.path.join(RAW, "meta.json")))
S_, W_, N_, E_ = meta["bbox"]
LAT0, LON0 = meta["center"]
phi = math.radians(LAT0)
MLAT = 111132.92 - 559.82 * math.cos(2 * phi) + 1.175 * math.cos(4 * phi)
MLON = 111412.84 * math.cos(phi) - 93.5 * math.cos(3 * phi)
def proj(lon, lat): return ((lon - LON0) * MLON, (LAT0 - lat) * MLAT)   # x east, z south
X0, Z0 = proj(W_, N_); X1, Z1 = proj(E_, S_)
STEP = float(sys.argv[3]) if len(sys.argv) > 3 else (2.5 if max(X1 - X0, Z1 - Z0) < 1000 else 5.0)

# ---- elevation mosaic (terrarium tiles)
tiles = [tuple(map(int, os.path.basename(f)[:-4].split("_"))) + (f,) for f in glob.glob(os.path.join(RAW, "dem", "*.png"))]
ZL = tiles[0][0]; TX0 = min(t[1] for t in tiles); TY0 = min(t[2] for t in tiles)
cols = max(t[1] for t in tiles) - TX0 + 1; rows = max(t[2] for t in tiles) - TY0 + 1
mos = np.zeros((rows * 256, cols * 256))
for _, tx, ty, f in tiles:
    a = (mimg.imread(f)[:, :, :3] * 255).round()
    mos[(ty - TY0) * 256:(ty - TY0 + 1) * 256, (tx - TX0) * 256:(tx - TX0 + 1) * 256] = a[:, :, 0] * 256 + a[:, :, 1] + a[:, :, 2] / 256 - 32768
def dem(lon, lat):
    n = 2 ** ZL * 256
    gx = (lon + 180) / 360 * n - TX0 * 256 - 0.5
    gy = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n - TY0 * 256 - 0.5
    gx = min(max(gx, 0), mos.shape[1] - 1.001); gy = min(max(gy, 0), mos.shape[0] - 1.001)
    x0, y0 = int(gx), int(gy); fx, fy = gx - x0, gy - y0
    v = mos[y0:y0 + 2, x0:x0 + 2]
    return v[0, 0] * (1 - fx) * (1 - fy) + v[0, 1] * fx * (1 - fy) + v[1, 0] * (1 - fx) * fy + v[1, 1] * fx * fy

nx = int(round((X1 - X0) / STEP)) + 1; nz = int(round((Z1 - Z0) / STEP)) + 1
grid = np.zeros((nz, nx))
for i in range(nz):
    for j in range(nx):
        x, z = X0 + j * STEP, Z0 + i * STEP
        grid[i, j] = dem(LON0 + x / MLON, LAT0 - z / MLAT)
g2 = grid.copy()
g2[1:-1, 1:-1] = sum(grid[1 + di:nz - 1 + di, 1 + dj:nx - 1 + dj] for di in (-1, 0, 1) for dj in (-1, 0, 1)) / 9
grid = g2
def hgt(x, z):
    gj = min(max((x - X0) / STEP, 0), nx - 1.001); gi = min(max((z - Z0) / STEP, 0), nz - 1.001)
    j, i = int(gj), int(gi); fx, fy = gj - j, gi - i
    v = grid[i:i + 2, j:j + 2]
    return float(v[0, 0] * (1 - fx) * (1 - fy) + v[0, 1] * fx * (1 - fy) + v[1, 0] * (1 - fx) * fy + v[1, 1] * fx * fy)

# ---- geometry helpers
def inside(pt, poly):
    x, y = pt; c = False
    for k in range(len(poly)):
        x1, y1 = poly[k]; x2, y2 = poly[k - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1: c = not c
    return c
def stitch(ways):
    segs = [list(w) for w in ways if len(w) > 1]; rings = []
    while segs:
        cur = segs.pop(0)
        while cur[0] != cur[-1]:
            for k, s in enumerate(segs):
                if s[0] == cur[-1]: cur += s[1:]; segs.pop(k); break
                if s[-1] == cur[-1]: cur += s[::-1][1:]; segs.pop(k); break
            else: break
        if len(cur) >= 4: rings.append(cur)
    return rings
def rings_of(e):
    if e["type"] == "way":
        g = [(p["lon"], p["lat"]) for p in e["geometry"]]
        return ([g] if len(g) >= 4 else []), []
    outs = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in e["members"] if m.get("role") == "outer" and "geometry" in m]
    ins = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in e["members"] if m.get("role") == "inner" and "geometry" in m]
    return stitch(outs), stitch(ins)
def xz(ring):
    pts = [proj(*p) for p in ring]
    if len(pts) > 1 and pts[0] == pts[-1]: pts = pts[:-1]
    return pts
def clip_poly(pts, m=8):
    def cl(ps, f, inter):
        out = []
        for k in range(len(ps)):
            a, b = ps[k - 1], ps[k]
            if f(b):
                if not f(a): out.append(inter(a, b))
                out.append(b)
            elif f(a): out.append(inter(a, b))
        return out
    ix = lambda c: (lambda a, b: (c, a[1] + (b[1] - a[1]) * (c - a[0]) / (b[0] - a[0])))
    iz = lambda c: (lambda a, b: (a[0] + (b[0] - a[0]) * (c - a[1]) / (b[1] - a[1]), c))
    ps = pts
    for f, g in ((lambda p: p[0] >= X0 - m, ix(X0 - m)), (lambda p: p[0] <= X1 + m, ix(X1 + m)),
                 (lambda p: p[1] >= Z0 - m, iz(Z0 - m)), (lambda p: p[1] <= Z1 + m, iz(Z1 + m))):
        if not ps: break
        ps = cl(ps, f, g)
    return ps
def r1(pts): return [[round(x, 1), round(z, 1)] for x, z in pts]
def num(v):
    try: return float(str(v).replace("m", "").strip())
    except Exception: return None

camp_ll, _ = rings_of(json.load(open(os.path.join(RAW, "campus.json")))["elements"][0])
camp = [xz(r) for r in camp_ll]
def in_campus(pt): return any(inside(pt, r) for r in camp)

area = json.load(open(os.path.join(RAW, "area.json")))["elements"]
buildings = []
for e in area:
    t = e.get("tags", {})
    if "building" not in t: continue
    outs, ins = rings_of(e)
    if not outs: continue
    outer = xz(max(outs, key=len)); holes = [xz(r) for r in ins]
    if len(outer) < 3: continue
    cx = sum(p[0] for p in outer) / len(outer); cz = sum(p[1] for p in outer) / len(outer)
    if not in_campus((cx, cz)): continue
    lv = num(t.get("building:levels")); h = num(t.get("height"))
    if lv is not None and lv < 1: lv = None
    canopy = t["building"] in ("roof", "carport")
    if h is None:
        h = 4.0 if canopy else (lv if lv is not None else 4) * 4.0
    samples = [hgt(x, z) for x, z in outer] + [hgt(cx, cz)]
    buildings.append(dict(id=f"{e['type']}/{e['id']}", n=t.get("name"), campus=True, kind=t["building"], lv=lv, h=round(h, 1),
                          g=round(sum(samples) / len(samples), 1), lo=round(min(samples), 1), o=r1(outer), ho=[r1(x) for x in holes if len(x) >= 3],
                          tagged=lv is not None or t.get("height") is not None))

# ---- OSM often stacks a building's outline and its parts as separate buildings.
# Coplanar roofs and walls then flicker, so merge near-duplicates and nudge the rest apart.
def fp_area(r): return abs(sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r))) / 2)
def bbox(b):
    xs = [p[0] for p in b["o"]]; zs = [p[1] for p in b["o"]]
    return min(xs), max(xs), min(zs), max(zs)
def overlap(a, b):
    A, B = bbox(a), bbox(b)
    x0, x1, z0, z1 = max(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), min(A[3], B[3])
    if x0 >= x1 or z0 >= z1: return 0.0
    hit = sum(1 for u in range(14) for v in range(14)
              if inside((x0 + (x1 - x0) * (u + .5) / 14, z0 + (z1 - z0) * (v + .5) / 14), a["o"])
              and inside((x0 + (x1 - x0) * (u + .5) / 14, z0 + (z1 - z0) * (v + .5) / 14), b["o"]))
    return (x1 - x0) * (z1 - z0) * hit / 196
for b in buildings: b["area"] = fp_area(b["o"])
buildings.sort(key=lambda b: -b["area"])
merged = dropped = nudged = 0
keep = []
for b in buildings:
    absorbed = False
    for k in keep:
        ov = overlap(k, b)
        if ov <= 1: continue
        frac = ov / max(1e-6, b["area"])
        if b["kind"] in ("roof", "carport") and frac > 0.3:
            absorbed = True; dropped += 1; break
        if frac > 0.85 and (abs(k["h"] - b["h"]) < 1.0 or not b["tagged"]):
            if not k["n"] and b["n"]: k["n"] = b["n"]
            if not k["tagged"] and b["tagged"]: k["h"], k["lv"], k["tagged"] = b["h"], b["lv"], True
            absorbed = True; merged += 1; break
        if abs(k["h"] - b["h"]) < 0.6:
            b["h"] = round(b["h"] + 0.6, 1); nudged += 1
    if not absorbed:
        if any(overlap(k, b) > 1 for k in keep):
            # shrink a nested part slightly so its walls do not sit on the outer walls
            cx = sum(p[0] for p in b["o"]) / len(b["o"]); cz = sum(p[1] for p in b["o"]) / len(b["o"])
            size = max(bbox(b)[1] - bbox(b)[0], bbox(b)[3] - bbox(b)[2], 1)
            f = max(0.9, 1 - 0.5 / size)
            b["o"] = [[round(cx + (x - cx) * f, 1), round(cz + (z - cz) * f, 1)] for x, z in b["o"]]
        keep.append(b)
for b in keep:
    b.pop("area", None); b.pop("tagged", None)
buildings = keep
print(f"overlaps: merged {merged}, dropped canopies {dropped}, nudged {nudged}")

ROAD_KEEP = {"primary", "secondary", "tertiary", "residential", "unclassified", "service", "pedestrian", "footway", "path", "steps", "living_street", "cycleway", "track"}
roads = []
for e in area:
    t = e.get("tags", {})
    if e["type"] != "way" or t.get("highway") not in ROAD_KEEP or t.get("area") == "yes": continue
    run = []
    for p in (proj(q["lon"], q["lat"]) for q in e["geometry"]):
        if X0 - 8 <= p[0] <= X1 + 8 and Z0 - 8 <= p[1] <= Z1 + 8: run.append(p)
        else:
            if len(run) > 1: roads.append(dict(k=t["highway"], n=t.get("name"), p=r1(run)))
            run = []
    if len(run) > 1: roads.append(dict(k=t["highway"], n=t.get("name"), p=r1(run)))

LAND = {"forest": "wood", "wood": "wood", "park": "park", "grass": "park", "garden": "park", "pitch": "pitch", "stadium": "pitch", "track": "pitch",
        "water": "water", "construction": "construction", "residential": "res", "playground": "park", "scrub": "wood", "meadow": "park"}
lands = []
for e in area:
    t = e.get("tags", {})
    if "building" in t or "highway" in t: continue
    k = LAND.get(t.get("leisure")) or LAND.get(t.get("natural")) or LAND.get(t.get("landuse"))
    if not k: continue
    outs, ins = rings_of(e)
    rings = [r1(r) for r in (clip_poly(xz(x)) for x in outs + ins) if len(r) >= 3]
    if rings: lands.append(dict(k=k, r=rings))

data = dict(meta=dict(lat=LAT0, lon=LON0),
            terrain=dict(x0=round(X0, 2), z0=round(Z0, 2), step=STEP, nx=nx, nz=nz, dm=[int(round(v * 10)) for v in grid.flatten()]),
            campus=[r1(r) for r in camp], buildings=buildings, roads=roads, lands=lands)
json.dump(data, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
named = [b for b in buildings if b["n"]]
print(f"extent {X1 - X0:.0f} x {Z1 - Z0:.0f} m, grid {nx} x {nz} @ {STEP} m, terrain {grid.min():.0f}-{grid.max():.0f} m")
print(f"buildings {len(buildings)} (named {len(named)}, with levels {sum(b['lv'] is not None for b in buildings)}, with height tag {sum(1 for e in area if 'building' in e.get('tags', {}) and 'height' in e['tags'])})")
print(f"roads {len(roads)}, land areas {len(lands)}, json {os.path.getsize(OUT) // 1024} KB")
