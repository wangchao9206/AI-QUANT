#!/bin/sh
set -eu

# Only public, content-hashed build files live here. HTML always comes from the image.
archive=/var/lib/nginx/asset-archive/assets
mkdir -p "$archive"
for asset in /usr/share/nginx/html/assets/*; do
    [ -f "$asset" ] || continue
    name=${asset##*/}
    [ ! -e "$archive/$name" ] || continue
    pending=$(mktemp "$archive/.incoming-XXXXXX")
    cp "$asset" "$pending"
    chmod 644 "$pending"
    mv "$pending" "$archive/$name"
done
