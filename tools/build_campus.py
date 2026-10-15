# Converts OSM + Terrarium DEM into local-meter JSON for the three.js page.
# usage: python -I build_data.py <data_dir> <out.json>
import json, math, sys, glob, os
import numpy as np
import matplotlib.image as mimg

D, OUT = sys.argv[1], sys.argv[2]
LAT0, LON0 = 37.5043853, 126.9567551          # campus centroid (OSM way 284355223)
phi = math.radians(LAT0)
MLAT = 111132.92 - 559.82*math.cos(2*phi) + 1.175*math.cos(4*phi)
MLON = 111412.84*math.cos(phi) - 93.5*math.cos(3*phi)
MARGIN = 45.0
S_, W_, N_, E_ = 37.5017743 - MARGIN/MLAT, 126.953878 - MARGIN/MLON, 37.5069963 + MARGIN/MLAT, 126.9596322 + MARGIN/MLON

def proj(lon, lat):
    return ((lon - LON0)*MLON, (LAT0 - lat)*MLAT)   # x east, z south

X0, Z0 = proj(W_, N_); X1, Z1 = proj(E_, S_)

# ---- DEM mosaic (z15 terrarium, tiles x 27939-27940, y 12696-12697)
Z = 15; TX0, TY0 = 27939, 12696
mos = np.zeros((512, 512))
for f in glob.glob(os.path.join(D, "dem", "15_*.png")):
    _, tx, ty = os.path.basename(f)[:-4].split("_")
    a = (mimg.imread(f)[:, :, :3]*255).round()
    e = a[:, :, 0]*256 + a[:, :, 1] + a[:, :, 2]/256 - 32768
    r, c = (int(ty)-TY0)*256, (int(tx)-TX0)*256
    mos[r:r+256, c:c+256] = e

def dem(lon, lat):
    n = 2**Z*256
    gx = (lon+180)/360*n - TX0*256 - 0.5
    gy = (1 - math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n - TY0*256 - 0.5
    x0, y0 = int(math.floor(gx)), int(math.floor(gy)); fx, fy = gx-x0, gy-y0
    v = mos[y0:y0+2, x0:x0+2]
    return (v[0,0]*(1-fx)*(1-fy) + v[0,1]*fx*(1-fy) + v[1,0]*(1-fx)*fy + v[1,1]*fx*fy)

STEP = 2.5
nx = int(round((X1-X0)/STEP)) + 1; nz = int(round((Z1-Z0)/STEP)) + 1
grid = np.zeros((nz, nx))
for i in range(nz):
    for j in range(nx):
        x, z = X0 + j*STEP, Z0 + i*STEP
        grid[i, j] = dem(LON0 + x/MLON, LAT0 - z/MLAT)
assert grid.min() > 0, grid.min()
# light 3x3 smoothing to soften the 30 m source steps
g2 = grid.copy()
g2[1:-1, 1:-1] = sum(grid[1+di:nz-1+di, 1+dj:nx-1+dj] for di in (-1,0,1) for dj in (-1,0,1))/9
grid = g2

def hgt(x, z):
    gj = min(max((x-X0)/STEP, 0), nx-1.001); gi = min(max((z-Z0)/STEP, 0), nz-1.001)
    j, i = int(gj), int(gi); fx, fy = gj-j, gi-i
    v = grid[i:i+2, j:j+2]
    return float(v[0,0]*(1-fx)*(1-fy) + v[0,1]*fx*(1-fy) + v[1,0]*(1-fx)*fy + v[1,1]*fx*fy)

# ---- OSM
area = json.load(open(os.path.join(D, "area.json")))["elements"]
camp_ll = [(p["lon"], p["lat"]) for p in json.load(open(os.path.join(D, "campus.json")))["elements"][0]["geometry"]]
camp = [proj(*p) for p in camp_ll]

def inside(pt, poly):
    x, y = pt; c = False
    for k in range(len(poly)):
        x1, y1 = poly[k]; x2, y2 = poly[k-1]
        if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/(y2-y1) + x1: c = not c
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

def xz(ring, closed=True):
    pts = [proj(*p) for p in ring]
    if closed and len(pts) > 1 and pts[0] == pts[-1]: pts = pts[:-1]
    return pts

def clip_poly(pts, m=8):
    # Sutherland-Hodgman against the bbox (+m metres)
    def cl(ps, inside_f, inter):
        out = []
        for k in range(len(ps)):
            a, b = ps[k-1], ps[k]
            ia, ib = inside_f(a), inside_f(b)
            if ib:
                if not ia: out.append(inter(a, b))
                out.append(b)
            elif ia: out.append(inter(a, b))
        return out
    def ix(c):  return lambda a, b: (c, a[1] + (b[1]-a[1])*(c-a[0])/(b[0]-a[0]))
    def iz(c):  return lambda a, b: (a[0] + (b[0]-a[0])*(c-a[1])/(b[1]-a[1]), c)
    ps = pts
    for f, g in ((lambda p: p[0] >= X0-m, ix(X0-m)), (lambda p: p[0] <= X1+m, ix(X1+m)),
                 (lambda p: p[1] >= Z0-m, iz(Z0-m)), (lambda p: p[1] <= Z1+m, iz(Z1+m))):
        if not ps: break
        ps = cl(ps, f, g)
    return ps

def r1(pts): return [[round(x, 1), round(z, 1)] for x, z in pts]

def num(v):
    try: return float(str(v).replace("m", "").strip())
    except Exception: return None

OVERRIDE = {  # facts from outside OSM
    "100주년기념관": dict(lv=12, ug=6, src="지하 6층·지상 12층 (대학저널 2016년 준공 보도)"),
}

buildings = []
for e in area:
    t = e.get("tags", {})
    if "building" not in t: continue
    outs, ins = rings_of(e)
    if not outs: continue
    outer = xz(max(outs, key=len))
    holes = [xz(r) for r in ins]
    cx = sum(p[0] for p in outer)/len(outer); cz = sum(p[1] for p in outer)/len(outer)
    if not (X0-20 < cx < X1+20 and Z0-20 < cz < Z1+20): continue
    is_camp = inside((cx, cz), camp)
    if not is_camp: continue
    name = t.get("name")
    lv = num(t.get("building:levels")); ug = num(t.get("building:levels:underground")); h = num(t.get("height"))
    src = None
    if name in OVERRIDE and is_camp:
        o = OVERRIDE[name]; lv, ug, src = o["lv"], o["ug"], o["src"]
    kind = t["building"]
    per = 4.0 if is_camp else 3.0
    est = False; hs = "tag"
    if h is None:
        hs = "lv"
        if lv is not None: h = lv*per
        else:
            hs = "est"
            est = True
            lv_guess = 4 if is_camp else (12 if kind == "apartments" else 2)
            h = lv_guess*per
    samples = [hgt(x, z) for x, z in outer] + [hgt(cx, cz)]
    ground = sum(samples)/len(samples)
    buildings.append(dict(
        id=f"{e['type']}/{e['id']}", n=name, en=t.get("name:en"), ref=t.get("alt_name"),
        lv=lv, ug=ug, h=round(h, 1), hs=hs, est=est, src=src, campus=is_camp, kind=kind,
        g=round(ground, 1), lo=round(min(samples), 1),
        o=r1(outer), ho=[r1(hh) for hh in holes if len(hh) >= 3]))

ROAD_KEEP = {"primary","secondary","tertiary","residential","unclassified","service","pedestrian","footway","path","steps","living_street","cycleway","track"}
roads = []
for e in area:
    t = e.get("tags", {})
    if e["type"] != "way" or t.get("highway") not in ROAD_KEEP: continue
    if t.get("area") == "yes": continue
    pts = [proj(p["lon"], p["lat"]) for p in e["geometry"]]
    run = []
    for p in pts:
        if X0-8 <= p[0] <= X1+8 and Z0-8 <= p[1] <= Z1+8: run.append(p)
        else:
            if len(run) > 1: roads.append(dict(k=t["highway"], n=t.get("name"), p=r1(run)))
            run = []
    if len(run) > 1: roads.append(dict(k=t["highway"], n=t.get("name"), p=r1(run)))

LAND = {"forest":"wood","wood":"wood","park":"park","grass":"park","garden":"park","pitch":"pitch","stadium":"pitch","track":"pitch","water":"water","construction":"construction","residential":"res","playground":"park"}
lands = []
for e in area:
    t = e.get("tags", {})
    if "building" in t or "highway" in t: continue
    k = LAND.get(t.get("leisure")) or LAND.get(t.get("natural")) or LAND.get(t.get("landuse"))
    if not k: continue
    outs, ins = rings_of(e)
    rings = [clip_poly(xz(r)) for r in outs] + [clip_poly(xz(r)) for r in ins]
    rings = [r1(r) for r in rings if len(r) >= 3]
    if rings: lands.append(dict(k=k, r=rings))

camp_xz = r1(xz(camp_ll))
data = dict(
    origin=dict(lat=LAT0, lon=LON0),
    terrain=dict(x0=round(X0, 2), z0=round(Z0, 2), step=STEP, nx=nx, nz=nz,
                 dm=[int(round(v*10)) for v in grid.flatten()]),
    campus=camp_xz, buildings=buildings, roads=roads, lands=lands)
json.dump(data, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))

# ---- report
print("extent m:", round(X1-X0), "x", round(Z1-Z0), "grid", nx, "x", nz)
print("terrain m:", round(grid.min(), 1), "-", round(grid.max(), 1))
cb = [b for b in buildings if b["campus"]]
print("buildings:", len(buildings), "campus:", len(cb), "estimated:", sum(b["est"] for b in buildings), "(campus est:", sum(b["est"] for b in cb), ")")
print("campus ground m:", min(b["g"] for b in cb), "-", max(b["g"] for b in cb))
north = grid[:nz//2].mean(); south = grid[nz//2:].mean(); west = grid[:, :nx//2].mean(); east = grid[:, nx//2:].mean()
print(f"mean elev N {north:.1f} S {south:.1f} W {west:.1f} E {east:.1f}")
print("roads:", len(roads), "lands:", len(lands), "json KB:", os.path.getsize(OUT)//1024)
for b in sorted(cb, key=lambda b: b["g"]):
    print(f"  {b['n'] or '(이름 없음)':12s} ref={b['ref']} lv={b['lv']} h={b['h']} est={b['est']} ground={b['g']}")
