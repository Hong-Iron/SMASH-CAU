# Builds site/index.html from src/app.html, data/campus.json and config.json.
# usage: python3 tools/assemble.py
import html, json, pathlib

root = pathlib.Path(__file__).resolve().parent.parent
cfg = json.loads((root / "config.json").read_text(encoding="utf-8"))
tpl = (root / "src" / "app.html").read_text(encoding="utf-8")
data = json.loads((root / "data" / "campus.json").read_text(encoding="utf-8"))
data["config"] = cfg
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
assert "__CAU_DATA__" in tpl and "__TITLE__" in tpl
page = tpl.replace("__CAU_DATA__", blob).replace("__TITLE__", html.escape(cfg["title"]))
head, rest = page.split('<div id="app">', 1)
e = lambda v: html.escape(v, quote=True)
icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
        "%3Ccircle cx='14' cy='19' r='10' fill='%231d1f22'/%3E"
        "%3Cpath d='M21 11l4-4' stroke='%23c2410c' stroke-width='3' stroke-linecap='round'/%3E"
        "%3Ccircle cx='27' cy='5' r='3' fill='%23ffb020'/%3E%3C/svg%3E")
url = cfg["url"]
doc = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{e(cfg['description'])}">
<meta property="og:title" content="{e(cfg['title'])}">
<meta property="og:description" content="{e(cfg['tagline'])}">
<meta property="og:type" content="website">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(url)}og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="{e(cfg['ogAlt'])}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{e(url)}og.png">
<link rel="icon" href="{icon}">
{head.strip()}
</head>
<body>
<div id="app">{rest.rstrip()}
</body>
</html>
"""
(root / "site" / "index.html").write_text(doc, encoding="utf-8")
print("site/index.html", len(doc.encode()) // 1024, "KB")
