# Cleans the elevation grid in data/campus.json in place:
#   1. fills no-data holes (values below 0 m),
#   2. removes spikes left by tall buildings in the SRTM surface model (higher than everything 45 m around),
#   3. levels each lake or pond to one water height with gently sloping banks,
# then re-seats buildings on the new ground and drops trees standing in water.
# usage: python3 tools/fix_terrain.py data/campus.json      (needs numpy)
import json, sys
import numpy as np

path = sys.argv[1]
d = json.load(open(path)); T = d["terrain"]; st = T["step"]
nz, nx = T["nz"], T["nx"]; x0, z0 = T["x0"], T["z0"]
g = np.array(T["dm"], dtype=float).reshape(nz, nx) / 10
before = g.copy()

# 1. holes
bad = g < 0
holes = int(bad.sum())
while bad.any():
    vals = np.where(bad, 0.0, g); cnt = (~bad).astype(float)
    s = np.zeros_like(g); n = np.zeros_like(g)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            s += np.roll(np.roll(vals, di, 0), dj, 1); n += np.roll(np.roll(cnt, di, 0), dj, 1)
    fill = bad & (n > 0)
    if not fill.any(): g[bad] = np.median(g[~bad]); break
    g[fill] = s[fill] / n[fill]; bad &= ~fill

# 2. spikes
r = max(1, int(round(45 / st)))
spikes = 0
for _ in range(3):
    pad = np.pad(g, r, mode="edge")
    ring = np.stack([pad[r + int(round(r * np.sin(a))):r + int(round(r * np.sin(a))) + nz, r + int(round(r * np.cos(a))):r + int(round(r * np.cos(a))) + nx]
                     for a in np.linspace(0, 2 * np.pi, 16, endpoint=False)])
    top = ring.max(0)
    flag = g - top > 12
    if not flag.any(): break
    spikes += int(flag.sum()); g[flag] = top[flag]

# 3. water
X = x0 + np.arange(nx) * st; Z = z0 + np.arange(nz) * st
GX, GZ = np.meshgrid(X, Z)
def inside(poly):
    poly = np.asarray(poly, dtype=float); res = np.zeros(GX.shape, bool)
    for k in range(len(poly)):
        (x1, z1), (x2, z2) = poly[k], poly[k - 1]
        cond = (z1 > GZ) != (z2 > GZ)
        with np.errstate(divide="ignore", invalid="ignore"):
            xc = (x2 - x1) * (GZ - z1) / (z2 - z1) + x1
        res ^= cond & (GX < xc)
    return res
def edge_dist(poly, mask):
    poly = np.asarray(poly, dtype=float); best = np.full(GX.shape, np.inf)
    for k in range(len(poly)):
        (ax, az), (bx, bz) = poly[k - 1], poly[k]
        dx, dz = bx - ax, bz - az; L = dx * dx + dz * dz or 1e-9
        t = np.clip(((GX - ax) * dx + (GZ - az) * dz) / L, 0, 1)
        best = np.minimum(best, np.hypot(GX - ax - t * dx, GZ - az - t * dz))
    return np.where(mask, best, np.inf)
BANK = 12.0
water_all = np.zeros(GX.shape, bool); lakes = 0
for L in d["lands"]:
    if L["k"] != "water": continue
    m = np.zeros(GX.shape, bool)
    for ring_ in L["r"]: m ^= inside(ring_)
    if m.sum() < 3: continue
    level = float(np.percentile(g[m], 20))
    g[m] = level - 0.6
    xs = [q[0] for rr in L["r"] for q in rr]; zs = [q[1] for rr in L["r"] for q in rr]
    FAR = 150.0
    near = (~m) & (GX > min(xs) - FAR) & (GX < max(xs) + FAR) & (GZ > min(zs) - FAR) & (GZ < max(zs) + FAR)
    dist = np.full(GX.shape, np.inf)
    for ring_ in L["r"]: dist = np.minimum(dist, edge_dist(ring_, near))
    # a shore much higher than the land farther out is a surface-model artifact, not a real cliff
    shore, outer = near & (dist < 40), near & (dist >= 40) & (dist < FAR)
    if outer.sum() > 10:
        cap = float(np.percentile(g[outer], 95)) + 2
        clamped = shore & (g > cap)
        spikes += int(clamped.sum()); g[clamped] = cap
    bank = near & (dist < BANK)
    t = dist[bank] / BANK; t = t * t * (3 - 2 * t)
    g[bank] = np.minimum(g[bank], level + (g[bank] - level) * t)
    water_all |= m; lakes += 1

T["dm"] = [int(round(v * 10)) for v in g.flatten()]

# re-seat buildings and drop trees in water
def hgt(x, z):
    gj = min(max((x - x0) / st, 0), nx - 1.001); gi = min(max((z - z0) / st, 0), nz - 1.001)
    j, i = int(gj), int(gi); fx, fz = gj - j, gi - i
    v = g[i:i + 2, j:j + 2]
    return float(v[0, 0] * (1 - fx) * (1 - fz) + v[0, 1] * fx * (1 - fz) + v[1, 0] * (1 - fx) * fz + v[1, 1] * fx * fz)
moved = 0
for b in d["buildings"]:
    cx = sum(p[0] for p in b["o"]) / len(b["o"]); cz = sum(p[1] for p in b["o"]) / len(b["o"])
    sm = [hgt(x, z) for x, z in b["o"]] + [hgt(cx, cz)]
    ng, nlo = round(sum(sm) / len(sm), 1), round(min(sm), 1)
    if abs(ng - b["g"]) > 0.5: moved += 1
    b["g"], b["lo"] = ng, nlo
wet = 0
if "trees" in d:
    keep = []
    for t_ in d["trees"]:
        j = int(round((t_[0] - x0) / st)); i = int(round((t_[1] - z0) / st))
        if 0 <= i < nz and 0 <= j < nx and water_all[i, j]: wet += 1; continue
        keep.append(t_)
    d["trees"] = keep
json.dump(d, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
diff = np.abs(g - before)
print(f"holes filled {holes}, spike cells {spikes}, lakes leveled {lakes}, buildings re-seated {moved}, trees removed from water {wet}, "
      f"terrain now {g.min():.0f}-{g.max():.0f} m, max change {diff.max():.0f} m")
