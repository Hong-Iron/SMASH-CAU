# 캠퍼스 정보: 이 학교 지도 자료(data/campus.json)와 허브에서 받은 이웃 정보(data/about.json)로
# 게임 위에 여는 '캠퍼스 정보' 창을 만든다. 검색 로봇이 읽도록 HTML에 처음부터 들어 있고, 버튼을 누르면 보인다.
# tools/assemble.py가 부른다: css, button, section = render(cfg, data, about)
import html, math, re

e = lambda v: html.escape(str(v), quote=True)
# 학교 땅 안에 있어도 학교 건물이 아닌 것(아파트, 주택, 공사 중 …)은 사실 목록과 건물 목록에서 뺀다
NOT_CAMPUS = {"apartments", "residential", "house", "detached", "semidetached_house", "terrace", "construction", "garage", "garages",
              "shed", "hut", "roof", "commercial", "retail", "industrial", "warehouse", "hotel", "kiosk", "service", "carport",
              "greenhouse", "static_caravan", "ruins", "bunker", "transformer_tower", "toilets"}
PITCH = 105 * 68   # 축구장 한 면(㎡)
# 건물 목록에 넣지 않는 부대시설 이름
UTILITY = ("엘리베이터", "승강기", "경비실", "화장실", "기계실", "전기실", "변전", "쓰레기", "분리수거", "흡연", "주차장 출입구")

def ring_area(r):
    return abs(sum(r[i][0] * r[(i + 1) % len(r)][1] - r[(i + 1) % len(r)][0] * r[i][1] for i in range(len(r)))) / 2

def batchim(word):   # 끝 글자에 받침이 있나 (조사 고르기). 숫자·로마자는 읽는 소리로 어림한다
    w = word.strip().rstrip(")）]").strip()
    if not w: return False
    c = w[-1]
    if "가" <= c <= "힣": return (ord(c) - 0xAC00) % 28 != 0
    if c.isdigit(): return c in "013678"
    return c.lower() in "lmn"

def j(word, with_b, without_b):   # j("성심교정", "은", "는") → "은"
    return with_b if batchim(word) else without_b

def man(v):   # 145,000 → "14.5만"
    return f"{v / 10000:.1f}".rstrip("0").rstrip(".") + "만"

def render(cfg, data, about):
    campus = cfg.get("campusName") or cfg.get("fullName") or cfg["title"]
    school = cfg.get("school") or campus
    code = cfg.get("code", "")
    B = data.get("buildings", [])
    A = {id(b): ring_area(b["o"]) - sum(ring_area(h) for h in b.get("ho", [])) for b in B}   # 바닥 넓이(㎡), 자료는 건드리지 않는다
    real = [b for b in B if b.get("kind") not in NOT_CAMPUS]
    named = {}
    for b in real:   # 같은 이름은 가장 높은 동 하나로
        n = (b.get("n") or "").strip()
        if n and A[id(b)] >= 30 and not any(u in n for u in UTILITY) and (n not in named or b.get("h", 0) > named[n].get("h", 0)): named[n] = b   # 30 ㎡ 아래(승강기탑, 경비실 …)는 목록에서 뺀다
    named = sorted(named.values(), key=lambda b: (-b.get("h", 0), b["n"]))
    tall = max(real, key=lambda b: b.get("h", 0)) if real else None
    big = max((b for b in real if b.get("n")), key=lambda b: A[id(b)], default=None)
    rings = data.get("campus") or []
    area = sum(ring_area(r) for r in rings) if rings and isinstance(rings[0][0][0], (int, float)) else 0
    gs = [b["g"] for b in real if isinstance(b.get("g"), (int, float))]
    lo, hi = (min(gs), max(gs)) if gs else (None, None)
    floor = sum(A[id(b)] * (b.get("lv") or max(1, round(b.get("h", 3.5) / 3.5))) for b in real)
    guessed = sum(1 for b in real if not b.get("lv"))
    roads = sorted({r["n"].strip() for r in data.get("roads", []) if (r.get("n") or "").strip()})
    region, name_en = about.get("region", ""), about.get("nameEn", "")
    rank, total = about.get("rank"), about.get("total")

    # ---------- 첫 문단: 이 학교에서만 맞는 문장들 ----------
    lead = [f"{e(campus)}{'(' + e(name_en) + ')' if name_en else ''}{j(campus, '은', '는')} {e(region)}에 있는 캠퍼스예요." if region
            else f"{e(campus)}{j(campus, '을', '를')} 3D로 옮긴 게임이에요."]
    lead.append(f"게임 속 캠퍼스에는 건물 {len(B):,}동이 서 있고{f', 그중 {len(named):,}동은 이름이 붙어 있어요' if named else ''}."
                + ((f" 건물 수로는 SMASH 대학교 {total}곳 가운데 가장 많아요." if rank == 1 else f" 건물 수로는 SMASH 대학교 {total}곳 가운데 {rank}번째로 많아요." if rank <= total // 3 else f" 건물 수로 보면 SMASH 대학교 {total}곳 가운데 {rank}번째 규모예요.") if rank and total else ""))
    if tall and tall.get("n"):
        lead.append(f"가장 높은 건물은 {e(tall['n'])}(약 {tall['h']:.0f} m{f', 지상 {int(tall['lv'])}층' if tall.get('lv') else ''}){j(tall['n'], '이에요', '예요')}.")
    if lo is not None:
        d = hi - lo
        if d >= 40: lead.append(f"캠퍼스 안 땅 높이가 해발 {lo:.0f} m에서 {hi:.0f} m까지 {d:.0f} m나 차이 나는 언덕 캠퍼스라, 위쪽 건물을 부수면 잔해가 비탈을 따라 굴러 내려가요.")
        elif d >= 8: lead.append(f"캠퍼스 안 땅 높이는 해발 {lo:.0f}~{hi:.0f} m로, 완만한 비탈 위에 건물들이 놓여 있어요.")
        else: lead.append(f"캠퍼스 땅은 해발 {(lo + hi) / 2:.0f} m 안팎으로 거의 평평해요.")
    if cfg.get("antipode"):
        lead.append(f"건물을 계속 부수며 땅을 파 내려가면 지구 반대편 {e(cfg['antipode'])}까지 닿아요.")

    facts = []
    if region: facts.append(("위치", e(region)))
    if area: facts.append(("캠퍼스 넓이", f"약 {man(area)} ㎡ (축구장 약 {max(1, round(area / PITCH)):,}개)"))
    facts.append(("건물", f"{len(B):,}동" + (f" (이름 있는 건물 {len(named):,}동)" if named else "")))
    if tall: facts.append(("가장 높은 건물", f"{e(tall.get('n') or '이름 없는 건물')} · 약 {tall['h']:.0f} m"))
    if big: facts.append(("가장 넓은 건물", f"{e(big['n'])} · 바닥 약 {round(A[id(big)], -1):,.0f} ㎡"))
    if floor: facts.append(("건물 바닥 넓이 합", f"약 {man(floor)} ㎡ (층수로 어림)"))
    if lo is not None: facts.append(("땅 높이", f"해발 {lo:.0f}~{hi:.0f} m"))
    if cfg.get("antipode"): facts.append(("지구 반대편", e(cfg["antipode"])))
    if about.get("added"):
        y, m, d = (int(x) for x in about["added"][:10].split("-"))
        facts.append(("게임에 들어온 날", f"{y}년 {m}월 {d}일"))
    facts_html = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in facts)

    def rows(bs):
        return "".join(f"<tr><td>{e(b['n'])}</td><td>{int(b['lv']) if b.get('lv') else '–'}</td><td>{b.get('h', 0):.0f}</td></tr>" for b in bs)
    head = "<thead><tr><th>이름</th><th>층</th><th>높이(m)</th></tr></thead>"
    TOP = 12
    blist = ""
    if named:
        blist = (f'<h3>건물 목록</h3><p>이름이 있는 건물을 높은 순서로 적었어요. 층수가 없는 건물은 지도에 층수가 적혀 있지 않아 높이를 어림한 거예요.</p>'
                 f'<table>{head}<tbody>{rows(named[:TOP])}</tbody></table>')
        if len(named) > TOP:
            blist += f'<details><summary>나머지 {len(named) - TOP:,}동 더 보기</summary><table>{head}<tbody>{rows(named[TOP:])}</tbody></table></details>'
    road_html = (f"<h3>캠퍼스 둘레의 길</h3><p>{', '.join(e(r) for r in roads[:14])}{' 등' if len(roads) > 14 else ''}. "
                 f"게임 속 길도 같은 이름으로 그려져 있어요.</p>") if roads else ""
    near = about.get("nearby") or []
    near_html = ("<h3>가까운 캠퍼스</h3><ul class=\"near\">" + "".join(
        f'<li><a href="/SMASH-{e(n["code"])}/">{e(n["campus"])}</a> <span>{n["km"]:.1f} km</span></li>' for n in near) + "</ul>") if near else ""
    made = (f"<h3>이렇게 만들었어요</h3><p>건물 모양과 층수, 길과 운동장은 OpenStreetMap 기여자들이 그린 지도에서, 땅 높낮이는 AWS Terrain Tiles(SRTM 30 m)에서 가져왔어요."
            + (f" 층수가 적혀 있지 않은 건물 {guessed:,}동은 높이를 어림해서 세웠어요." if guessed else "")
            + " 건물 겉모습은 실제 사진이 아니라 건물 종류에 맞춘 일반 재질이에요. 이름이나 모양이 실제와 다르면 "
            + f'<a href="https://github.com/Hong-Iron/hong-iron.github.io/issues/new?title={e("건물 고침: " + campus)}" target="_blank" rel="noopener">고쳐 달라고 알려 주세요</a>.</p>')
    play = ("<h3>하는 법</h3><ul><li>건물을 누르면 아래 도구판에서 고른 무기로 부서져요. 숫자 1~7로도 무기를 바꿀 수 있어요.</li>"
            "<li>한 손가락으로 끌면 화면이 움직이고, 두 손가락으로 돌리거나 확대해요. PC에서는 끌기와 휠을 써요.</li>"
            f"<li>부순 점수는 {e(school)} 이름으로 학교 대항 랭킹에 더해져요. 되돌리기와 전부 복구로 언제든 다시 세울 수 있어요.</li></ul>")
    foot = ('<p class="foot"><a href="/">SMASH 대학교 전체 캠퍼스 보기</a> · 학교와 관계없는 비공식 팬 게임이에요. 학교 로고와 교표는 쓰지 않아요.</p>')

    nb = lambda t: re.sub(r"(\d) (m|㎡|km)(?![A-Za-z])", "\\1\u00a0\\2", t)   # 숫자와 단위가 줄에서 갈라지지 않게
    section = (f'<section id="campus-info" class="cinfo" role="dialog" aria-modal="true" aria-labelledby="cinfo-title" hidden>'
               f'<div class="sheet"><button type="button" class="x" id="cinfo-close" aria-label="닫기">&times;</button>'
               f'<h2 id="cinfo-title">{e(campus)}</h2><p class="sub">{e(name_en) + " · " if name_en else ""}SMASH {e(code)}</p>'
               f'<p>{nb(" ".join(lead))}</p><dl>{nb(facts_html)}</dl>{blist}{road_html}{nb(near_html)}{nb(made)}{play}{foot}'
               f'<button type="button" class="go" id="cinfo-go">부수러 가기</button></div></section>\n'
               + SCRIPT)
    button = '<a class="hub-link cinfo-link" id="cinfo-link" href="#campus-info">캠퍼스 정보</a>'
    return CSS, button, section

CSS = """<style>
.cinfo { position: fixed; inset: 0; z-index: 60; display: flex; align-items: flex-start; justify-content: center; padding: max(16px, env(safe-area-inset-top)) 12px max(16px, env(safe-area-inset-bottom)); background: rgba(8, 10, 14, .55); overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch; touch-action: pan-y; }
.cinfo[hidden] { display: none; }
.cinfo .sheet { position: relative; width: min(640px, 100%); margin: auto 0; padding: 22px 20px 20px; border-radius: 14px; background: #fff; color: #1c2128; font: 15px/1.65 var(--font-ui, system-ui, sans-serif); box-shadow: 0 18px 50px rgba(0, 0, 0, .35); }
.cinfo h2 { margin: 0 36px 2px 0; font-size: 21px; line-height: 1.3; }
.cinfo .sub { margin: 0 0 12px; color: #5b6573; font-size: 13px; }
.cinfo h3 { margin: 22px 0 6px; font-size: 16px; }
.cinfo p { margin: 0 0 8px; }
.cinfo dl { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; margin: 14px 0 0; padding: 12px 14px; border-radius: 10px; background: #f3f5f8; font-size: 14px; }
.cinfo dt { color: #5b6573; }
.cinfo dd { margin: 0; }
.cinfo table { width: 100%; border-collapse: collapse; font-size: 14px; }
.cinfo th, .cinfo td { padding: 5px 6px; border-bottom: 1px solid #e3e7ec; text-align: right; }
.cinfo th:first-child, .cinfo td:first-child { text-align: left; }
.cinfo th { color: #5b6573; font-weight: 600; }
.cinfo details { margin-top: 8px; }
.cinfo summary { cursor: pointer; color: #2457c5; padding: 4px 0; }
.cinfo ul { margin: 0; padding-left: 20px; }
.cinfo .near { list-style: none; padding: 0; display: grid; gap: 4px; }
.cinfo .near span { color: #5b6573; font-size: 13px; }
.cinfo a { color: #2457c5; }
.cinfo .foot { margin-top: 18px; color: #5b6573; font-size: 13px; }
.cinfo .x { position: absolute; top: 10px; right: 10px; width: 36px; height: 36px; border: 0; border-radius: 50%; background: #eef1f5; color: #1c2128; font-size: 22px; line-height: 1; cursor: pointer; }
.cinfo .go { display: block; width: 100%; margin-top: 16px; padding: 12px; border: 0; border-radius: 10px; background: #1c2128; color: #fff; font: 700 15px/1.2 var(--font-ui, system-ui, sans-serif); cursor: pointer; }
@media (prefers-color-scheme: dark) {
  .cinfo .sheet { background: #1b1f26; color: #e8ebef; }
  .cinfo .sub, .cinfo dt, .cinfo th, .cinfo .near span, .cinfo .foot { color: #9aa4b2; }
  .cinfo dl { background: #252a33; }
  .cinfo th, .cinfo td { border-color: #303642; }
  .cinfo a, .cinfo summary { color: #8ab4ff; }
  .cinfo .x { background: #2a303a; color: #e8ebef; }
  .cinfo .go { background: #e8ebef; color: #1b1f26; }
}
</style>
"""

SCRIPT = """<script>
(() => {
  const box = document.getElementById('campus-info'), link = document.getElementById('cinfo-link');
  if (!box) return;
  let back = null;
  const open = (push) => { if (!box.hidden) return; back = document.activeElement; box.hidden = false; box.scrollTop = 0;
    if (push && location.hash !== '#campus-info') history.pushState(null, '', '#campus-info'); document.getElementById('cinfo-close').focus(); };
  const close = () => { if (box.hidden) return; box.hidden = true;
    if (location.hash === '#campus-info') history.replaceState(null, '', location.pathname + location.search);
    if (back && back.focus) back.focus(); };
  if (link) link.addEventListener('click', (ev) => { ev.preventDefault(); open(true); });
  document.getElementById('cinfo-close').addEventListener('click', close);
  document.getElementById('cinfo-go').addEventListener('click', close);
  box.addEventListener('click', (ev) => { if (ev.target === box) close(); });
  addEventListener('keydown', (ev) => { if (!box.hidden) { ev.stopPropagation(); if (ev.key === 'Escape') close(); } }, true);
  addEventListener('hashchange', () => { location.hash === '#campus-info' ? open(false) : close(); });
  if (location.hash === '#campus-info') open(false);
})();
</script>
"""
