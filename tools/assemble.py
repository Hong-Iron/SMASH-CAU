# Builds site/index.html from src/app.html and data/campus.json.
# usage: python3 tools/assemble.py
import pathlib

root = pathlib.Path(__file__).resolve().parent.parent
tpl = (root / "src" / "app.html").read_text(encoding="utf-8")
data = (root / "data" / "campus.json").read_text(encoding="utf-8")
assert "__CAU_DATA__" in tpl
page = tpl.replace("__CAU_DATA__", data.replace("</", "<\\/"))
head, rest = page.split('<div id="app">', 1)
icon = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
        "%3Ccircle cx='14' cy='19' r='10' fill='%231d1f22'/%3E"
        "%3Cpath d='M21 11l4-4' stroke='%23c2410c' stroke-width='3' stroke-linecap='round'/%3E"
        "%3Ccircle cx='27' cy='5' r='3' fill='%23ffb020'/%3E%3C/svg%3E")
html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="중앙대학교 서울캠퍼스를 3D로 부수고 지구 중심까지 파 내려가는 스트레스 해소 게임">
<meta property="og:title" content="SMASH CAU">
<meta property="og:description" content="중앙대를 부셔 (시험기간 스트레스 해소)">
<meta property="og:type" content="website">
<meta property="og:url" content="https://hong-iron.github.io/SMASH-CAU/">
<meta property="og:image" content="https://hong-iron.github.io/SMASH-CAU/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="폭탄이 터지며 무너지는 중앙대 서울캠퍼스 3D 화면과 SMASH CAU 제목">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="https://hong-iron.github.io/SMASH-CAU/og.png">
<link rel="icon" href="{icon}">
{head.strip()}
</head>
<body>
<div id="app">{rest.rstrip()}
</body>
</html>
"""
(root / "site" / "index.html").write_text(html, encoding="utf-8")
print("site/index.html", len(html.encode()) // 1024, "KB")
