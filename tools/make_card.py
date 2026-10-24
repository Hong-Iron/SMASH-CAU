"""site/og.png(1200×630) → site/card.webp(600×315), 허브 학교 카드와 지도 옆 패널에 쓰는 작은 썸네일.

og.png는 공유 미리보기용으로 그대로 두고, 허브는 이 파일을 불러 전송량을 줄인다.
실행: ~/.venvs/vault-plots/bin/python tools/make_card.py   (Pillow, WebP 지원 필요)
og.png를 새로 만들면 이것도 다시 실행한다.
"""
import pathlib
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "site" / "og.png"
DST = ROOT / "site" / "card.webp"
SIZE = (600, 315)
QUALITY = 72


def main():
    img = Image.open(SRC).convert("RGB")
    img = img.resize(SIZE, Image.LANCZOS)
    img.save(DST, "WEBP", quality=QUALITY, method=6)
    kb = DST.stat().st_size / 1024
    print(f"{DST.relative_to(ROOT)} {SIZE[0]}x{SIZE[1]} {kb:.0f} KB")
    if kb > 120:
        sys.exit("card.webp가 120KB를 넘는다 — QUALITY를 낮춘다")


if __name__ == "__main__":
    main()
