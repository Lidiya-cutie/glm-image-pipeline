#!/usr/bin/env python3
"""
Композиция макетов категории «дискредитация» без SDXL: сплошной/пастельный фон + текстовый оверлей
(аналог tobacco_composition_with_products.py, но без пачек, логотипов и бейджей заведений).

Пример:
    cp configs/discreditation_config.example.json configs/discreditation_config.json
    python scripts/discreditation_composition.py --count 3 --format horizontal
    python scripts/discreditation_composition.py --scenario placeholder_01 --headline "локальный текст"
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.discreditation_overlay import (
    apply_discreditation_overlay,
    build_discreditation_text_bundle,
    get_layout_by_name,
    load_scenarios,
    reload_config,
)

BANNER_FORMATS = {"square": (1024, 1024), "horizontal": (1200, 700), "vertical": (800, 1200)}

DEFAULT_CONFIG_EXAMPLE = PROJECT_ROOT / "configs" / "discreditation_config.example.json"


def _ensure_config_exists() -> None:
    path = PROJECT_ROOT / "configs" / "discreditation_config.json"
    if path.is_file():
        return
    if DEFAULT_CONFIG_EXAMPLE.is_file():
        print(
            f"Создайте {path.name}:\n"
            f"  cp configs/discreditation_config.example.json configs/discreditation_config.json"
        )
    sys.exit(1)


def create_solid_background(width: int, height: int) -> Image.Image:
    colors = [(240, 238, 235), (45, 45, 50), (60, 55, 50), (52, 52, 58)]
    bg = random.choice(colors)
    return Image.new("RGBA", (width, height), (*bg, 255))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Композиция «дискредитация»: фон + заголовок/описание/дисклеймер (без SDXL)"
    )
    parser.add_argument("--output", type=str, default="output/discreditation_composition")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS.keys()), default="horizontal")
    parser.add_argument("--scenario", type=str, help="Иначе случайный сценарий на каждый кадр")
    parser.add_argument("--headline", type=str, default=None)
    parser.add_argument("--description", type=str, default=None)
    parser.add_argument("--disclaimer", type=str, default=None)
    parser.add_argument("--layout", type=str)
    args = parser.parse_args()

    _ensure_config_exists()
    reload_config()
    scenarios = load_scenarios()
    if not scenarios:
        print("Нет сценариев в discreditation_config.json")
        sys.exit(1)

    w, h = BANNER_FORMATS[args.format]
    out_path = Path(args.output)
    out_path.mkdir(parents=True, exist_ok=True)
    layout = get_layout_by_name(args.layout) if args.layout else None

    print(f"Генерация {args.count} макетов, format={args.format}")
    for i in range(args.count):
        sc = next((s for s in scenarios if s["name"] == args.scenario), None) if args.scenario else None
        if sc is None:
            sc = random.choice(scenarios)
        bundle = build_discreditation_text_bundle(
            headline=args.headline,
            description=args.description,
            disclaimer=args.disclaimer,
            scenario=sc,
        )
        bg = create_solid_background(w, h)
        final = apply_discreditation_overlay(bg, bundle, scenario=sc, layout=layout)
        ts = int(time.time() * 1000)
        fname = f"discreditation_{sc['name'].replace(' ', '_')}_{i:03d}_{ts}.png"
        final.save(out_path / fname, quality=95)
        print(f"[{i + 1}/{args.count}] {fname}")

    print(f"\nГотово: {out_path}")


if __name__ == "__main__":
    main()
