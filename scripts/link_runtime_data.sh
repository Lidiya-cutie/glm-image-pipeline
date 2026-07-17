#!/usr/bin/env bash
# Symlink runtime media from the working data tree into this repo (media stays out of git).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${GLM_DATA_ROOT:-/mldata/glm-image-pipeline}"

if [[ ! -d "$SRC" ]]; then
  echo "GLM_DATA_ROOT not found: $SRC"
  echo "Export GLM_DATA_ROOT=/path/to/media-tree (cigarette_images, fonts, baby_logo, ...)"
  exit 1
fi

link_one() {
  local name="$1"
  local target="$SRC/$name"
  local dest="$ROOT/$name"
  if [[ ! -e "$target" ]]; then
    echo "skip missing: $target"
    return 0
  fi
  if [[ -L "$dest" || -e "$dest" ]]; then
    rm -rf "$dest"
  fi
  ln -sfn "$target" "$dest"
  echo "linked $dest -> $target"
}

link_one cigarette_images
link_one fonts
link_one baby_logo
link_one baby_logo_1
link_one alcohol_free_icons_clean
link_one alcohol_free_icons_2
link_one alcohol_free_icons_2_clean

echo "QR generator (optional): export PYTHONPATH=/mldata/custom-qr-generator:\$PYTHONPATH"
echo "Done. Category scripts resolve assets via PROJECT_ROOT/<name>."
