#!/usr/bin/env bash
# Сборка tar.gz для переноса circular_frame на другой сервер (из корня glm-image-pipeline).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-circular_frame_bundle_$(date +%Y%m%d_%H%M%S).tar.gz}"
cd "$ROOT"
tar -czvf "$OUT" \
  scripts/generate_circular_frame_banners.py \
  scripts/circular_frame_composition.py \
  scripts/pack_circular_frame_bundle.sh \
  pipeline/__init__.py \
  pipeline/inference/__init__.py \
  pipeline/inference/simple_pipeline.py \
  pipeline/inference/pipeline.py \
  configs/circular_frame_config.example.json \
  requirements-circular-frame.txt
echo "OK: $ROOT/$OUT"
echo "Скопируйте также configs/circular_frame_config.json с рабочего сервера (не в архиве)."
