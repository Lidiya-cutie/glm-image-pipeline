#!/usr/bin/env python3
"""
Генерация изображений в стиле «круг в белом поле + чёрная окантовка + секторы прорыва».

Паттерн как у alcomarket / folk / lombard / baby_food: SDXL → постобработка.
Текстовый оверлей не обязателен (чисто визуальный арт / макет).

  cp configs/circular_frame_config.example.json configs/circular_frame_config.json
  python scripts/generate_circular_frame_banners.py --list-scenarios
  python scripts/generate_circular_frame_banners.py --all-scenarios --count 1 --output output/circular_frame
  python scripts/generate_circular_frame_banners.py --scenario round_action_snow_01
  python scripts/generate_circular_frame_banners.py --without-people --all-scenarios
  python scripts/generate_circular_frame_banners.py --with-people --scenarios space_marine_snowmobile,samurai_duel_petals
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.circular_frame_composition import apply_circular_frame_from_config

CONFIG_PATH = PROJECT_ROOT / "configs" / "circular_frame_config.json"

BANNER_FORMATS = {
    "square": (1024, 1024),
    "horizontal": (1200, 700),
    "vertical": (800, 1200),
}

NEG_PROMPT = (
    "text, words, letters, watermark, logo, ugly, low quality, blurry, deformed, "
    "cluttered frame, square frame, thick black bars"
)
NEG_PROMPT_PERSON = (
    NEG_PROMPT
    + ", extra limbs, bad anatomy, deformed hands, fused fingers, wrong face, lowres portrait"
)

# Принудительная геометрия для всех сценариев этого пайплайна:
# фон/сцена генерируются внутри окружности, снаружи — пустое светлое поле.
FORCED_CIRCULAR_SUFFIX = (
    " Strict composition constraint: all meaningful scene content and background must stay inside "
    "a clearly outlined central circle. Outside the circle keep a clean uniform plain background, "
    "white or very light gray, with no environment details or textures. "
    "No text, no watermark, no logo."
)


def _load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.is_file():
        ex = PROJECT_ROOT / "configs" / "circular_frame_config.example.json"
        if ex.is_file():
            print(
                f"Нет {CONFIG_PATH.name}. Скопируйте example:\n"
                f"  cp configs/circular_frame_config.example.json configs/circular_frame_config.json"
            )
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_scenarios() -> List[Dict[str, Any]]:
    cfg = _load_config()
    return list(cfg.get("scenarios") or [])


def compose_full_prompt(scenario: Dict[str, Any], global_suffix: str) -> str:
    base = str(scenario.get("prompt") or "").strip()
    if "prompt_suffix" in scenario:
        s = str(scenario.get("prompt_suffix") or "").strip()
    else:
        s = str(global_suffix or "").strip()
    forced = FORCED_CIRCULAR_SUFFIX.strip()
    parts = [base]
    if forced:
        parts.append(forced)
    if s:
        parts.append(s)
    return " ".join(p for p in parts if p).strip()


class CircularFramePipeline:
    def __init__(
        self,
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        quantize: Optional[str] = None,
    ) -> None:
        self.device = device
        self.dtype = dtype
        self.quantize = quantize
        self._pipeline = None

    def load(self) -> None:
        if self._pipeline is not None:
            return
        from pipeline.inference.simple_pipeline import SimpleImagePipeline

        print("Загрузка SDXL…")
        self._pipeline = SimpleImagePipeline(
            device=self.device,
            dtype=self.dtype,
            quantize=self.quantize,
        )
        self._pipeline.load()

    def generate_raw(
        self,
        prompt: str,
        width: int,
        height: int,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
    ) -> Image.Image:
        self.load()
        neg = negative_prompt or NEG_PROMPT
        return self._pipeline.generate(
            prompt=prompt,
            negative_prompt=neg,
            width=width,
            height=height,
            num_inference_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            num_images=1,
        )[0]

    def generate_framed(
        self,
        scenario: Dict[str, Any],
        config: Dict[str, Any],
        width: int,
        height: int,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
    ) -> Image.Image:
        global_suffix = str(config.get("prompt_template_suffix") or "")
        full_prompt = compose_full_prompt(scenario, global_suffix)
        has_person = bool(
            scenario.get("has_person")
            or scenario.get("person_position")
        )
        neg = NEG_PROMPT_PERSON if has_person else NEG_PROMPT
        raw = self.generate_raw(
            full_prompt,
            width,
            height,
            num_steps,
            guidance_scale,
            seed,
            negative_prompt=neg,
        )
        return apply_circular_frame_from_config(
            raw.convert("RGBA"),
            scenario.get("framing"),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SDXL + круглая рамка на белом фоне (секторы прорыва по конфигу)"
    )
    parser.add_argument("--scenario", type=str, help="Имя сценария")
    parser.add_argument("--all-scenarios", action="store_true")
    parser.add_argument("--scenarios", type=str, help="Через запятую")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS.keys()), default="square")
    parser.add_argument("--width", type=int)
    parser.add_argument("--height", type=int)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--cfg-scale", type=float, default=7.5)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--raw-only", action="store_true", help="Только SDXL без круглой маски")
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"])
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--dtype", type=str, default="fp16", choices=["fp16", "bf16", "fp32"])
    parser.add_argument("--cpu", action="store_true", help="device=cpu")
    parser.add_argument("--output", type=str, default="output/circular_frame")
    parser.add_argument("--list-scenarios", action="store_true")
    parser.add_argument(
        "--with-people",
        action="store_true",
        help="Только сценарии с has_person / person_position",
    )
    parser.add_argument(
        "--without-people",
        action="store_true",
        help="Только сценарии без людей",
    )
    args = parser.parse_args()

    cfg = _load_config()
    scenarios = load_scenarios()
    if args.list_scenarios:
        if not scenarios:
            print("Сценарии пусты — создайте configs/circular_frame_config.json")
        else:
            for s in scenarios:
                hp = s.get("has_person") or s.get("person_position")
                tag = "с людьми" if hp else "без людей"
                print(f"  • {s.get('name')} ({tag})")
        return

    if not scenarios:
        sys.exit(1)

    if args.with_people and args.without_people:
        print("Нельзя одновременно --with-people и --without-people")
        sys.exit(1)

    if args.all_scenarios:
        selected = scenarios
    elif args.scenarios:
        names = [n.strip() for n in args.scenarios.split(",") if n.strip()]
        selected = [s for s in scenarios if s.get("name") in names]
    elif args.scenario:
        selected = [s for s in scenarios if s.get("name") == args.scenario]
        if not selected:
            print(f"Сценарий {args.scenario!r} не найден")
            sys.exit(1)
    else:
        selected = [random.choice(scenarios)]

    if args.with_people:
        selected = [
            s
            for s in selected
            if s.get("has_person") or s.get("person_position")
        ]
    elif args.without_people:
        selected = [
            s
            for s in selected
            if not (s.get("has_person") or s.get("person_position"))
        ]

    if not selected:
        print("После фильтра не осталось сценариев.")
        sys.exit(1)

    w, h = (args.width, args.height) if args.width and args.height else BANNER_FORMATS[args.format]
    device = "cpu" if args.cpu else args.device
    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    pl = CircularFramePipeline(
        device=device,
        dtype=dtype_map[args.dtype],
        quantize=args.quantize,
    )

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    n = 0
    for sc in selected:
        for i in range(args.count):
            n += 1
            seed = args.seed if args.seed is not None else random.randint(1, 2**31 - 1)
            ts = int(time.time() * 1000)
            base = str(sc.get("name", "scenario")).replace(" ", "_")
            try:
                if args.raw_only:
                    pl.load()
                    prompt = compose_full_prompt(sc, str(cfg.get("prompt_template_suffix") or ""))
                    hp = bool(sc.get("has_person") or sc.get("person_position"))
                    neg = NEG_PROMPT_PERSON if hp else NEG_PROMPT
                    print(f"[{n}] raw: {sc.get('name')} …")
                    img = pl.generate_raw(
                        prompt, w, h, args.steps, args.cfg_scale, seed, negative_prompt=neg
                    )
                    name = f"circular_raw_{base}_{i:03d}_{ts}.png"
                else:
                    print(f"[{n}] framed: {sc.get('name')} …")
                    img = pl.generate_framed(sc, cfg, w, h, args.steps, args.cfg_scale, seed)
                    name = f"circular_framed_{base}_{i:03d}_{ts}.png"
                p = out_dir / name
                img.save(p, quality=95)
                print(f"  ok {p}")
            except Exception as e:
                print(f"  error: {e}")
                import traceback

                traceback.print_exc()


if __name__ == "__main__":
    main()
