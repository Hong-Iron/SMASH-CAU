#!/bin/sh
# Downloads the raw OpenStreetMap data and elevation tiles that tools/build_campus.py reads.
# usage: sh tools/fetch.sh raw
set -e
D=${1:-raw}
mkdir -p "$D/dem"
OV=https://overpass-api.de/api/interpreter
UA='SMASH-CAU data build'
curl -sf -A "$UA" "$OV" --data-urlencode 'data=[out:json][timeout:60];way(284355223);out geom;' -o "$D/campus.json"
B='37.5004,126.9522,37.5083,126.9613'
curl -sf -A "$UA" "$OV" --data-urlencode "data=[out:json][timeout:90];(way[\"building\"]($B);relation[\"building\"]($B);way[\"building:part\"]($B);way[\"highway\"]($B);way[\"landuse\"]($B);way[\"leisure\"]($B);way[\"natural\"]($B);relation[\"natural\"]($B);relation[\"landuse\"]($B););out geom;" -o "$D/area.json"
for x in 27939 27940; do
  for y in 12696 12697; do
    curl -sf "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/15/$x/$y.png" -o "$D/dem/15_${x}_${y}.png"
  done
done
echo "saved to $D"
