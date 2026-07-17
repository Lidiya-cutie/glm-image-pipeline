#!/usr/bin/env python3
"""
Trust Management Clean Background Generator

Скрипт для генерации ЧИСТЫХ фонов доверительного управления без текста и QR.
Используется для последующей композиции в DualCompositionEngine.
"""

import argparse
import sys
from pathlib import Path
import json
import torch
import time
from PIL import Image
from typing import Dict, List, Optional, Any
import random

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_trust_management_banners import (
    TRUST_MANAGEMENT_SCENARIOS_NO_PEOPLE,
    TRUST_MANAGEMENT_SCENARIOS_WITH_PEOPLE,
    TRUST_MANAGEMENT_SCENARIOS,
    BANNER_FORMATS,
    NEG_PROMPT,
    NEG_PROMPT_PERSON,
)

# Промпты исключения для чистоты фона
CLEAN_NEG_PROMPT = "text, words, letters, watermark, logo, cartoon, anime, 3d render, cluttered, bright neon colors, low quality, blurry, deformed, signature, branding"
CLEAN_NEG_PROMPT_PERSON = "deformed, ugly, bad anatomy, extra limbs, blurry, low quality, cartoon, anime, watermark, text, words, painting, drawing"


class CleanTrustManagementGenerator:
    """
    Генератор чистых изображений для доверительного управления.
    """
    
    def __init__(
        self,
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        quantize: str = None,
        model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
    ):
        self.device = device
        self.dtype = dtype
        self.quantize = quantize
        self.model_id = model_id
        self._pipeline = None
        
    def load(self):
        """Загрузка пайплайна инференса."""
        if self._pipeline is not None:
            return
            
        from pipeline.inference.simple_pipeline import SimpleImagePipeline
        
        print(f"Загрузка модели {self.model_id}...")
        self._pipeline = SimpleImagePipeline(
            model_id=self.model_id,
            device=self.device,
            dtype=self.dtype,
            quantize=self.quantize,
        )
        self._pipeline.load()
        
    def generate(
        self,
        scenario: Dict[str, Any],
        width: int = 1024,
        height: int = 1024,
        steps: int = 40,
        cfg: float = 7.5,
        seed: Optional[int] = None,
    ) -> Image.Image:
        """Генерация одного чистого изображения."""
        self.load()
        
        prompt = scenario["prompt"]
        # Выбор негативного промпта в зависимости от наличия человека
        is_person = scenario.get("has_person") or scenario.get("person_position") or scenario.get("type") == "person"
        neg = CLEAN_NEG_PROMPT_PERSON if is_person else CLEAN_NEG_PROMPT
        
        if seed is None:
            seed = random.randint(0, 2**32 - 1)
            
        print(f"Генерация сценария: {scenario['name']} (Seed: {seed})")
        
        images = self._pipeline.generate(
            prompt=prompt,
            negative_prompt=neg,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=cfg,
            seed=seed,
            num_images=1,
        )
        
        return images[0]

    def mass_generate(
        self,
        count: int,
        output_dir: Path,
        width: int = 1024,
        height: int = 1024,
        steps: int = 40,
        cfg: float = 7.5,
        scenarios: List[Dict] = None,
    ):
        """Массовая генерация случайных сценариев."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        scenarios = scenarios or TRUST_MANAGEMENT_SCENARIOS
        
        print(f"Начинаю массовую генерацию {count} чистых фонов доверительного управления...")
        
        for i in range(count):
            scenario = random.choice(scenarios)
            image = self.generate(scenario, width, height, steps, cfg)
            
            timestamp = int(time.time())
            filename = f"trust_clean_{i:04d}_{scenario['name']}_{timestamp}.png"
            filepath = output_dir / filename
            
            image.save(filepath, quality=95)
            print(f"[{i+1}/{count}] Сохранено: {filepath}")


def main():
    parser = argparse.ArgumentParser(description="Clean Trust Management Background Generator")
    
    # Режимы генерации
    parser.add_argument("--count", type=int, default=1, help="Количество изображений")
    parser.add_argument("--scenario-name", type=str, help="Сгенерировать конкретный сценарий по имени")
    parser.add_argument("--list-scenarios", action="store_true", help="Показать список всех сценариев")
    parser.add_argument("--with-people", action="store_true", help="Только сценарии с людьми")
    parser.add_argument("--without-people", action="store_true", help="Только сценарии без людей")
    
    # Параметры изображения
    parser.add_argument("--format", type=str, choices=list(BANNER_FORMATS.keys()), default="square", help="Формат баннера")
    parser.add_argument("--width", type=int, help="Ширина (переопределяет --format)")
    parser.add_argument("--height", type=int, help="Высота (переопределяет --format)")
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--cfg", type=float, default=7.5)
    
    # Модель и устройство
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"], help="Квантование")
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--output", type=str, default="output/trust_management_clean_backgrounds")
    
    args = parser.parse_args()
    
    if args.list_scenarios:
        print("\n=== Доступные сценарии доверительного управления ===")
        print("\n[БЕЗ людей]:")
        for s in TRUST_MANAGEMENT_SCENARIOS_NO_PEOPLE:
            print(f"  - {s['name']}")
        print("\n[С людьми]:")
        for s in TRUST_MANAGEMENT_SCENARIOS_WITH_PEOPLE:
            print(f"  - {s['name']} ({s.get('person_position', '-')})")
        return

    # Определяем размеры
    if args.width and args.height:
        w, h = args.width, args.height
    else:
        w, h = BANNER_FORMATS[args.format]

    # Выбор сценариев
    if args.with_people:
        scenarios = TRUST_MANAGEMENT_SCENARIOS_WITH_PEOPLE
    elif args.without_people:
        scenarios = TRUST_MANAGEMENT_SCENARIOS_NO_PEOPLE
    else:
        scenarios = TRUST_MANAGEMENT_SCENARIOS

    # Запуск генератора
    generator = CleanTrustManagementGenerator(
        device=args.device,
        quantize=args.quantize
    )
    
    out_dir = Path(args.output)
    
    if args.scenario_name:
        # Генерация конкретного сценария
        target = [s for s in scenarios if s['name'] == args.scenario_name]
        if not target:
            print(f"Сценарий '{args.scenario_name}' не найден!")
            print(f"Доступные: {[s['name'] for s in scenarios]}")
            return
        for i in range(args.count):
            img = generator.generate(target[0], w, h, args.steps, args.cfg)
            img.save(out_dir / f"single_{args.scenario_name}_{i}_{int(time.time())}.png")
            print(f"[{i+1}/{args.count}] Сохранено: {out_dir / f'single_{args.scenario_name}_{i}_{int(time.time())}.png'}")
    else:
        # Случайная массовая генерация
        generator.mass_generate(args.count, out_dir, w, h, args.steps, args.cfg, scenarios=scenarios)


if __name__ == "__main__":
    main()
