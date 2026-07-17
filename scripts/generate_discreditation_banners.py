#!/usr/bin/env python3
"""
Генератор макетов категории «дискредитация» (SDXL + текстовый оверлей по образцу табака).

Промпты и строки заголовка/описания/дисклеймера в репозитории не заполняются — только в вашем
discreditation_config.json (скопируйте из discreditation_config.example.json).

Если prompt сценария пустой, SDXL не вызывается: рисуется нейтральный однотонный фон (можно
наложить пустой или заполненный локально текст). Для строгой проверки используйте --require-prompt.

Примеры:
    cp configs/discreditation_config.example.json configs/discreditation_config.json
    python scripts/generate_discreditation_banners.py --list-scenarios
    python scripts/generate_discreditation_banners.py --all-scenarios --count 1 --format horizontal
    python scripts/generate_discreditation_banners.py --scenario placeholder_01 --headline "..." --require-prompt
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.discreditation_overlay import (
    apply_discreditation_overlay,
    build_discreditation_text_bundle,
    compose_sdxl_prompt,
    get_layout_by_name,
    load_scenarios,
    reload_config,
)

BANNER_FORMATS = {
    "square": (1024, 1024),
    "horizontal": (1200, 700),
    "vertical": (800, 1200),
}

NEG_PROMPT = (
    "text, words, letters, watermark, logo, cartoon, anime, 3d render, "
    "low quality, blurry, deformed, ugly"
)

DEFAULT_CONFIG_EXAMPLE = PROJECT_ROOT / "configs" / "discreditation_config.example.json"


def _ensure_config_exists() -> None:
    path = PROJECT_ROOT / "configs" / "discreditation_config.json"
    if path.is_file():
        return
    if DEFAULT_CONFIG_EXAMPLE.is_file():
        print(
            f"Файл {path.name} не найден. Скопируйте example:\n"
            f"  cp configs/discreditation_config.example.json configs/discreditation_config.json"
        )
    else:
        print(f"Нет конфига: {path}")
    sys.exit(1)


class DiscreditationBannerPipeline:
    def __init__(
        self,
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        quantize: Optional[str] = None,
    ):
        self.device = device
        self.dtype = dtype
        self.quantize = quantize
        self._pipeline = None

    def load(self) -> None:
        if self._pipeline is not None:
            return
        from pipeline.inference.simple_pipeline import SimpleImagePipeline

        print("Загрузка SDXL...")
        self._pipeline = SimpleImagePipeline(
            device=self.device,
            dtype=self.dtype,
            quantize=self.quantize,
        )
        self._pipeline.load()

    def generate_background(
        self,
        prompt: str,
        width: int,
        height: int,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
    ) -> Image.Image:
        self.load()
        images = self._pipeline.generate(
            prompt=prompt,
            negative_prompt=NEG_PROMPT,
            width=width,
            height=height,
            num_inference_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            num_images=1,
        )
        return images[0]

    @staticmethod
    def neutral_background(width: int, height: int) -> Image.Image:
        return Image.new("RGB", (width, height), (52, 52, 58))


def generate_banner(
    pipeline: DiscreditationBannerPipeline,
    scenario: Dict[str, Any],
    *,
    width: int,
    height: int,
    headline: Optional[str],
    description: Optional[str],
    disclaimer: Optional[str],
    layout_name: Optional[str],
    num_steps: int,
    guidance_scale: float,
    seed: Optional[int],
    backgrounds_only: bool,
    require_prompt: bool,
    use_prompt_detail_suffix: bool = True,
    no_disclaimer: bool = False,
) -> Image.Image:
    raw_prompt = str(scenario.get("prompt", "") or "").strip()
    if not raw_prompt:
        if require_prompt:
            raise ValueError(f"Сценарий '{scenario.get('name')}': пустой prompt (--require-prompt)")
        background = pipeline.neutral_background(width, height)
    else:
        sdxl_prompt = compose_sdxl_prompt(scenario, use_detail_suffix=use_prompt_detail_suffix)
        background = pipeline.generate_background(
            sdxl_prompt,
            width=width,
            height=height,
            num_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )

    if backgrounds_only:
        return background.convert("RGB")

    bundle = build_discreditation_text_bundle(
        headline=headline,
        description=description,
        disclaimer=disclaimer,
        scenario=scenario,
        no_disclaimer=no_disclaimer,
    )
    layout = get_layout_by_name(layout_name) if layout_name else None
    return apply_discreditation_overlay(
        background.convert("RGBA"),
        bundle,
        scenario=scenario,
        layout=layout,
    ).convert("RGB")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Генератор макетов категории «дискредитация» (SDXL + текст, без пачек/бейджей)"
    )
    parser.add_argument("--scenario", type=str)
    parser.add_argument("--all-scenarios", action="store_true")
    parser.add_argument("--scenarios", type=str, help="Через запятую")
    parser.add_argument("--exclude-scenarios", type=str)
    parser.add_argument("--with-people", action="store_true")
    parser.add_argument("--without-people", action="store_true")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--headline", type=str, default=None)
    parser.add_argument("--description", type=str, default=None)
    parser.add_argument("--disclaimer", type=str, default=None)
    parser.add_argument("--layout", type=str)
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS.keys()), default="horizontal")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--cfg-scale", type=float, default=7.5)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--backgrounds-only", action="store_true")
    parser.add_argument("--require-prompt", action="store_true", help="Ошибка, если prompt сценария пустой")
    parser.add_argument(
        "--no-prompt-detail-suffix",
        action="store_true",
        help="Не добавлять prompt_detail_suffix из конфига к prompt (только сырой prompt сценария)",
    )
    parser.add_argument(
        "--no-disclaimer",
        action="store_true",
        help="Без дисклеймера и без тёмной полосы снизу (не использовать пул disclaimers из конфига)",
    )
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"])
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--dtype", type=str, default="fp16", choices=["fp16", "bf16", "fp32"])
    parser.add_argument("--cpu", action="store_true")
    parser.add_argument("--output", type=str, default="output/discreditation")
    parser.add_argument("--list-scenarios", action="store_true")
    args = parser.parse_args()

    _ensure_config_exists()
    reload_config()
    scenarios = load_scenarios()
    if not scenarios:
        print("В discreditation_config.json нет сценариев.")
        sys.exit(1)

    if args.list_scenarios:
        print("\n=== Сценарии (дискредитация) ===")
        for s in scenarios:
            person = "с человеком" if s.get("has_person") else "без людей"
            pq = "есть" if str(s.get("prompt", "")).strip() else "пустой prompt"
            print(f"  • {s['name']} ({person}, {pq})")
        return

    if args.all_scenarios:
        selected = scenarios
    elif args.scenarios:
        names = [n.strip() for n in args.scenarios.split(",")]
        selected = [s for s in scenarios if s["name"] in names]
        if len(selected) != len(names):
            found = {s["name"] for s in selected}
            print(f"Не найдены: {set(names) - found}")
    elif args.scenario:
        selected = [s for s in scenarios if s["name"] == args.scenario]
        if not selected:
            print(f"Сценарий '{args.scenario}' не найден.")
            sys.exit(1)
    else:
        selected = [random.choice(scenarios)]

    if args.with_people:
        selected = [s for s in selected if s.get("has_person")]
    elif args.without_people:
        selected = [s for s in selected if not s.get("has_person")]

    if args.exclude_scenarios:
        ex = {n.strip() for n in args.exclude_scenarios.split(",") if n.strip()}
        selected = [s for s in selected if s["name"] not in ex]

    if not selected:
        print("Нет сценариев после фильтрации.")
        sys.exit(1)

    if args.width and args.height:
        w, h = args.width, args.height
    else:
        w, h = BANNER_FORMATS[args.format]

    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    dtype = torch.float32 if args.cpu else dtype_map[args.dtype]
    device = "cpu" if args.cpu else args.device
    pipe = DiscreditationBannerPipeline(device=device, dtype=dtype, quantize=args.quantize)

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    n = 0
    for scenario in selected:
        for i in range(args.count):
            n += 1
            seed = args.seed if args.seed is not None else random.randint(100000, 999999)
            ts = int(time.time() * 1000)
            base = scenario["name"].replace(" ", "_")
            try:
                label = "Фон" if args.backgrounds_only else "Баннер"
                hint = ""
                if not args.backgrounds_only and not str(scenario.get("prompt", "")).strip():
                    hint = " [нейтральный фон: prompt пустой]"
                print(f"[{n}] {label}: {scenario['name']}{hint}...")

                img = generate_banner(
                    pipe,
                    scenario,
                    width=w,
                    height=h,
                    headline=args.headline,
                    description=args.description,
                    disclaimer=args.disclaimer,
                    layout_name=args.layout,
                    num_steps=args.steps,
                    guidance_scale=args.cfg_scale,
                    seed=seed,
                    backgrounds_only=args.backgrounds_only,
                    require_prompt=args.require_prompt,
                    use_prompt_detail_suffix=not args.no_prompt_detail_suffix,
                    no_disclaimer=args.no_disclaimer,
                )
                suffix = "_bg" if args.backgrounds_only else ""
                fname = f"discreditation{suffix}_{base}_{i:03d}_{ts}.png"
                path = out_dir / fname
                img.save(path, quality=95)
                print(f"  ✅ {path}")
            except Exception as e:
                print(f"  ❌ {e}")
                import traceback

                traceback.print_exc()

    print(f"\n✅ Готово: {out_dir}")


if __name__ == "__main__":
    main()
