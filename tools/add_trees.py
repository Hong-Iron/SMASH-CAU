# Adds deterministic tree positions (in wood/park areas, away from buildings and roads) and trims fields.
# usage: python3 tools/add_trees.py <in.json> <out.json>
import json, math, random, sys
d = json.load(open(sys.argv[1]))
rnd = random.Random(84)
T = d["terrain"]; X0, Z0 = T["x0"], T["z0"]; X1 = X0 + (T["nx"]-1)*T["step"]; Z1 = Z0 + (T["nz"]-1)*T["step"]

def inside(x, z, ring):
    c = False; n = len(ring)
    for k in range(n):
        x1, z1 = ring[k]; x2, z2 = ring[k-1]
        if (z1 > z) != (z2 > z) and x < (x2-x1)*(z-z1)/(z2-z1) + x1: c = not c
    return c
def in_rings(x, z, rings):
    return sum(inside(x, z, r) for r in rings) % 2 == 1

# spatial hash for buildings and road segments
CELL = 25
def key(x, z): return (int(math.floor(x/CELL)), int(math.floor(z/CELL)))
bgrid = {}
for i, b in enumerate(d["buildings"]):
    xs = [p[0] for p in b["o"]]; zs = [p[1] for p in b["o"]]
    for gx in range(int(math.floor((min(xs)-3)/CELL)), int(math.floor((max(xs)+3)/CELL))+1):
        for gz in range(int(math.floor((min(zs)-3)/CELL)), int(math.floor((max(zs)+3)/CELL))+1):
            bgrid.setdefault((gx, gz), []).append(i)
RW = {"tertiary": 9, "secondary": 11, "primary": 13, "residential": 6, "unclassified": 6, "living_street": 5, "service": 4,
      "pedestrian": 4.5, "track": 3, "footway": 2, "cycleway": 2, "path": 1.6, "steps": 2.6}
rgrid = {}
for r in d["roads"]:
    w = RW.get(r["k"], 3)/2 + 1.6
    for a, b in zip(r["p"], r["p"][1:]):
        for gx in range(int(math.floor((min(a[0], b[0])-w)/CELL)), int(math.floor((max(a[0], b[0])+w)/CELL))+1):
            for gz in range(int(math.floor((min(a[1], b[1])-w)/CELL)), int(math.floor((max(a[1], b[1])+w)/CELL))+1):
                rgrid.setdefault((gx, gz), []).append((a, b, w))
def seg_d(px, pz, a, b):
    ax, az = a; bx, bz = b; dx, dz = bx-ax, bz-az
    L = dx*dx + dz*dz
    t = 0 if L == 0 else max(0, min(1, ((px-ax)*dx + (pz-az)*dz)/L))
    return math.hypot(px-ax-t*dx, pz-az-t*dz)
def blocked(x, z):
    k = key(x, z)
    for i in bgrid.get(k, []):
        b = d["buildings"][i]
        if in_rings(x, z, [b["o"]] + b["ho"]) or any(seg_d(x, z, p, q) < 2.5 for p, q in zip(b["o"], b["o"][1:] + b["o"][:1])):
            return True
    return any(seg_d(x, z, a, b) < w for a, b, w in rgrid.get(k, []))

DENS = {"wood": 1/38, "park": 1/140}
trees = []
for L in d["lands"]:
    if L["k"] not in DENS: continue
    rings = L["r"]
    xs = [p[0] for r in rings for p in r]; zs = [p[1] for r in rings for p in r]
    bx0, bx1 = max(min(xs), X0+4), min(max(xs), X1-4); bz0, bz1 = max(min(zs), Z0+4), min(max(zs), Z1-4)
    if bx0 >= bx1 or bz0 >= bz1: continue
    n = int((bx1-bx0)*(bz1-bz0)*DENS[L["k"]])
    for _ in range(n):
        x = rnd.uniform(bx0, bx1); z = rnd.uniform(bz0, bz1)
        if in_rings(x, z, rings) and not blocked(x, z):
            trees.append([round(x, 1), round(z, 1), round(rnd.uniform(0.75, 1.3), 2)])
# street trees along campus roads
STREET = {"tertiary", "residential", "service", "pedestrian", "living_street", "unclassified"}
for r in d["roads"]:
    if r["k"] not in STREET: continue
    off = RW.get(r["k"], 4)/2 + 2.2
    for a, b in zip(r["p"], r["p"][1:]):
        L = math.hypot(b[0]-a[0], b[1]-a[1])
        if L < 1: continue
        ux, uz = (b[0]-a[0])/L, (b[1]-a[1])/L
        t = rnd.uniform(0, 9)
        while t < L:
            for side in (-1, 1):
                if rnd.random() < 0.45: continue
                x = a[0] + ux*t - uz*off*side; z = a[1] + uz*t + ux*off*side
                if X0+3 < x < X1-3 and Z0+3 < z < Z1-3 and not blocked(x, z):
                    trees.append([round(x, 1), round(z, 1), round(rnd.uniform(0.7, 1.05), 2)])
            t += rnd.uniform(9, 13)
# drop near-duplicates (overlapping wood polygons)
seen = set(); out = []
for t in trees:
    k = (round(t[0]/2.5), round(t[1]/2.5))
    if k in seen: continue
    seen.add(k); out.append(t)
MAX_TREES = 7000   # keeps big campuses (and their forests) light enough to draw
if len(out) > MAX_TREES:
    out = sorted(rnd.sample(out, MAX_TREES))
d["trees"] = out

json.dump(d, open(sys.argv[2], "w"), ensure_ascii=False, separators=(",", ":"))
import os
print("trees:", len(out), "json KB:", os.path.getsize(sys.argv[2])//1024)
holes = [(b["n"], len(b["ho"])) for b in d["buildings"] if b["ho"]]
print("buildings with holes:", holes)
print("max footprint pts:", max(len(b["o"]) for b in d["buildings"]))
