# Floors and heights from the national building register (건축물대장 표제부, data.go.kr BldRgstHubService).
# usage: python3 tools/floors.py [--refresh]
#   1. fetch: for every parcel in config.json "parcels", saves the register rows to data/floors.json
#      (needs DATA_GO_KR_KEY in .env at the repo root; the key never goes into git or the data file)
#   2. apply: matches rows to OSM buildings in data/campus.json by name and sets lv / h
# A name matches when one cleaned name contains the other; a building with two or more candidate rows is left alone.
import json, os, pathlib, re, ssl, sys, urllib.parse, urllib.request

root = pathlib.Path(__file__).resolve().parent.parent
cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
camp_p, floors_p = root / "data" / "campus.json", root / "data" / "floors.json"
API = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"


def key():
    env = root / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATA_GO_KR_KEY="): return line.split("=", 1)[1].strip()
    if os.environ.get("DATA_GO_KR_KEY"): return os.environ["DATA_GO_KR_KEY"]
    sys.exit("DATA_GO_KR_KEY is missing: put it in .env (git-ignored)")


def get(url):
    try: return urllib.request.urlopen(url, timeout=30).read()
    except urllib.error.URLError as e:
        if "CERTIFICATE" not in str(e): raise
        # python.org builds on macOS ship without CA certificates
        import subprocess
        return subprocess.run(["curl", "-s", "--max-time", "30", url], capture_output=True, check=True).stdout


def fetch():
    k, rows = key(), []
    for pc in cfg.get("parcels", []):
        page = 1
        while True:
            q = dict(serviceKey=k, sigunguCd=pc["sigunguCd"], bjdongCd=pc["bjdongCd"], platGbCd=pc.get("platGbCd", "0"),
                     bun=pc["bun"], ji=pc.get("ji", "0000"), numOfRows=100, pageNo=page, _type="json")
            body = json.loads(get(API + "?" + urllib.parse.urlencode(q)))["response"]["body"]
            items = (body.get("items") or {}).get("item") or []
            items = items if isinstance(items, list) else [items]
            for x in items:
                rows.append({f: x.get(f) for f in ("mgmBldrgstPk", "platPlc", "dongNm", "bldNm", "mainPurpsCdNm", "grndFlrCnt", "ugrndFlrCnt", "heit")})
            if page * 100 >= int(body.get("totalCount") or 0): break
            page += 1
    floors_p.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"fetched {len(rows)} register rows from {len(cfg.get('parcels', []))} parcel(s)")


def clean(s):
    s = re.sub(r"\(.*?\)", "", s or "")
    return re.sub(r"\s+|및|관리동", "", s)


def apply():
    rows = json.loads(floors_p.read_text(encoding="utf-8"))
    data = json.loads(camp_p.read_text(encoding="utf-8"))
    names = [(r, [c for c in (clean(r["bldNm"]), clean(r["dongNm"])) if len(c) >= 2]) for r in rows]
    changed = 0
    for b in data["buildings"]:
        n = clean(b.get("n"))
        if len(n) < 2: continue
        exact = [r for r, cs in names if n in cs]
        cand = exact or [r for r, cs in names if any(n in c or c in n for c in cs)]
        if len(cand) != 1:
            if len(cand) > 1: print(f"  {b['n']}: {len(cand)} candidates, left alone")
            continue
        r = cand[0]
        lv = int(r["grndFlrCnt"] or 0)
        if lv < 1: continue
        h = float(r["heit"] or 0)
        h = round(h if h >= lv * 2.5 else lv * 4.0, 1)
        if b.get("lv") != lv or abs(b["h"] - h) > 0.05:
            print(f"  {b['n']}: {b.get('lv')}층 {b['h']} m -> {lv}층 {h} m ({r['bldNm'].strip() or r['dongNm']})")
            b["lv"], b["h"], changed = lv, h, changed + 1
    # hand-checked overrides for buildings whose register row could not be matched by name
    for b in data["buildings"]:
        m = cfg.get("floorsManual", {}).get(b["id"])
        if m and (b.get("lv") != m["lv"] or abs(b["h"] - m["h"]) > 0.05):
            print(f"  {b['n'] or b['id']}: {b.get('lv')}층 {b['h']} m -> {m['lv']}층 {m['h']} m (manual: {m.get('note', '')})")
            b["lv"], b["h"], changed = m["lv"], m["h"], changed + 1
    camp_p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"updated {changed} building(s)")


if __name__ == "__main__":
    if "--refresh" in sys.argv or not floors_p.exists(): fetch()
    apply()
