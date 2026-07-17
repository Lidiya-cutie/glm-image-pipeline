#!/usr/bin/env python3
"""
Full Ad Banner Generation Pipeline

Генерация рекламных баннеров: фон + наложение текста.

Примеры:
    # Один баннер
    python scripts/generate_ad_banners.py --scenario courthouse --output output/ads/

    # Все сценарии с текстом
    python scripts/generate_ad_banners.py --all-scenarios --output output/ads/

    # С кастомным текстом
    python scripts/generate_ad_banners.py --scenario library \
        --headline "Ваш адвокат" \
        --description "Опыт более 20 лет" \
        --phone "+7 (999) 123-45-67"

    # Все комбинации (сценарий × лейаут × стиль)
    python scripts/generate_ad_banners.py --all-combinations --max-combinations 10

    # С квантизацией
    python scripts/generate_ad_banners.py --all-scenarios --quantize 4bit
"""

import argparse
import sys
from pathlib import Path
import random
import json
from typing import Dict, List, Optional, Any
import torch
from PIL import Image

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.text_overlay import (
    BannerOverlay,
    LAYOUTS,
    TEXT_STYLES,
    DEFAULT_HEADLINES,
    DEFAULT_DESCRIPTIONS,
    DEFAULT_DISCLAIMERS,
    generate_phone,
    get_layout_by_name,
    get_style_by_name,
)
from scripts.generate_banners import (
    BannerGenerator,
    SCENARIOS_BACKGROUND,
    SCENARIOS_WITH_PERSON,
    NEG_PROMPT,
    NEG_PROMPT_PERSON,
)


class AdBannerPipeline:
    """
    Full pipeline: Background generation + Text overlay.
    """
    
    def __init__(
        self,
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        quantize: str = None,
    ):
        self.generator = BannerGenerator(
            device=device,
            dtype=dtype,
            quantize=quantize,
        )
    
    def generate_ad_banner(
        self,
        scenario: Dict[str, Any],
        headline: str = None,
        description: str = None,
        phone: str = None,
        disclaimer: str = None,
        layout: Dict[str, Any] = None,
        style: Dict[str, Any] = None,
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: int = None,
        add_card_bg: bool = True,
    ) -> Image.Image:
        """
        Generate a complete ad banner with background and text.
        
        Args:
            scenario: Background scenario config
            headline: Main headline (random if None)
            description: Description text (random if None)
            phone: Phone number (random if None)
            disclaimer: Disclaimer (random if None)
            layout: Layout config (random if None)
            style: Style config (random if None)
            width, height: Image dimensions
            num_inference_steps: Diffusion steps
            guidance_scale: CFG scale
            seed: Random seed
            add_card_bg: Add semi-transparent background for text
            
        Returns:
            PIL Image with complete banner
        """
        # Select layout based on scenario (person side awareness)
        if layout is None:
            layout = self._select_layout_for_scenario(scenario)
        
        # Random selections
        style = style or random.choice(TEXT_STYLES)
        headline = headline or random.choice(DEFAULT_HEADLINES)
        description = description or random.choice(DEFAULT_DESCRIPTIONS)
        phone = phone or generate_phone()
        disclaimer = disclaimer or random.choice(DEFAULT_DISCLAIMERS)
        
        # Generate background
        background = self.generator.generate_from_scenario(
            scenario=scenario,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )
        
        # Apply text overlay
        overlay = BannerOverlay(layout=layout, style=style)
        result = overlay.apply(
            background,
            headline=headline,
            description=description,
            phone=phone,
            disclaimer=disclaimer,
            add_card_bg=add_card_bg,
        )
        
        return result
    
    def _select_layout_for_scenario(self, scenario: Dict) -> Dict:
        """Select appropriate layout based on scenario."""
        if 'person_side' in scenario:
            side = scenario['person_side']
            if side == "right":
                # Text on left
                candidates = [l for l in LAYOUTS if l['name'] in ['classic_left', 'diagonal']]
            elif side == "left":
                # Text on right
                candidates = [l for l in LAYOUTS if l['name'] in ['classic_right']]
            elif side == "bottom":
                # Text on top
                candidates = [l for l in LAYOUTS if l['name'] in ['top_bottom', 'center_stack']]
            else:
                candidates = LAYOUTS
        else:
            candidates = LAYOUTS
        
        return random.choice(candidates) if candidates else random.choice(LAYOUTS)
    
    def generate_batch(
        self,
        scenarios: List[Dict],
        output_dir: Path,
        variations_per_scenario: int = 1,
        layout: Dict = None,
        style: Dict = None,
        **kwargs,
    ) -> List[Dict]:
        """
        Generate multiple banners.
        
        Returns list of metadata dicts.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        count = 0
        
        for scenario in scenarios:
            for var in range(variations_per_scenario):
                count += 1
                print(f"\n[{count}] Generating: {scenario['name']} (variation {var+1})")
                
                # Use provided layout/style or select random
                use_layout = layout if layout else self._select_layout_for_scenario(scenario)
                use_style = style if style else random.choice(TEXT_STYLES)
                
                # Generate
                image = self.generate_ad_banner(
                    scenario=scenario,
                    layout=use_layout,
                    style=use_style,
                    **kwargs,
                )
                
                # Save
                filename = f"{scenario['name']}_{use_layout['name']}_{use_style['name']}_{var:02d}.png"
                filepath = output_dir / filename
                image.save(filepath, quality=95)
                
                results.append({
                    "filename": str(filepath),
                    "scenario": scenario['name'],
                    "layout": use_layout['name'],
                    "style": use_style['name'],
                })
                
                print(f"Saved: {filepath}")
        
        return results
    
    def generate_all_combinations(
        self,
        scenarios: List[Dict],
        output_dir: Path,
        max_combinations: int = None,
        layout: Dict = None,  # ignored, we iterate all
        style: Dict = None,   # ignored, we iterate all
        **kwargs,
    ) -> List[Dict]:
        """Generate all scenario × layout × style combinations."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        count = 0
        
        for scenario in scenarios:
            for iter_layout in LAYOUTS:
                for iter_style in TEXT_STYLES:
                    if max_combinations and count >= max_combinations:
                        return results
                    
                    count += 1
                    name = f"{scenario['name']}_{iter_layout['name']}_{iter_style['name']}"
                    print(f"\n[{count}] Generating: {name}")
                    
                    image = self.generate_ad_banner(
                        scenario=scenario,
                        layout=iter_layout,
                        style=iter_style,
                        **kwargs,
                    )
                    
                    filepath = output_dir / f"{name}.png"
                    image.save(filepath, quality=95)
                    
                    results.append({
                        "filename": str(filepath),
                        "scenario": scenario['name'],
                        "layout": iter_layout['name'],
                        "style": iter_style['name'],
                    })
        
        return results


def main():
    parser = argparse.ArgumentParser(description="Generate complete ad banners")
    
    # Scenario selection
    parser.add_argument("--scenario", type=str, help="Specific scenario name")
    parser.add_argument("--all-scenarios", action="store_true", help="Use all scenarios")
    parser.add_argument("--backgrounds-only", action="store_true", 
                        help="Only background scenarios (no people)")
    parser.add_argument("--with-people", action="store_true",
                        help="Only scenarios with people")
    
    # Text content
    parser.add_argument("--headline", type=str, help="Custom headline")
    parser.add_argument("--description", type=str, help="Custom description")
    parser.add_argument("--phone", type=str, help="Custom phone number")
    parser.add_argument("--disclaimer", type=str, help="Custom disclaimer")
    
    # Layout/Style
    parser.add_argument("--layout", type=str, 
                        choices=[l['name'] for l in LAYOUTS],
                        help="Specific layout")
    parser.add_argument("--style", type=str,
                        choices=[s['name'] for s in TEXT_STYLES],
                        help="Specific text style")
    parser.add_argument("--no-card-bg", action="store_true",
                        help="Disable card background")
    
    # Generation params
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--cfg-scale", type=float, default=7.5)
    parser.add_argument("--seed", type=int, default=None)
    
    # Batch options
    parser.add_argument("--variations", type=int, default=1,
                        help="Variations per scenario")
    parser.add_argument("--all-combinations", action="store_true",
                        help="Generate all scenario×layout×style combinations")
    parser.add_argument("--max-combinations", type=int, default=None,
                        help="Limit combinations")
    
    # Output
    parser.add_argument("--output", type=str, default="output/ads",
                        help="Output directory")
    parser.add_argument("--save-metadata", action="store_true",
                        help="Save metadata JSON")
    
    # Model
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"],
                        help="Quantization mode")
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--dtype", type=str, default="fp16",
                        choices=["fp16", "bf16", "fp32"])
    
    args = parser.parse_args()
    
    # Select scenarios
    if args.backgrounds_only:
        scenarios = SCENARIOS_BACKGROUND
    elif args.with_people:
        scenarios = SCENARIOS_WITH_PERSON
    else:
        scenarios = SCENARIOS_BACKGROUND + SCENARIOS_WITH_PERSON
    
    if args.scenario:
        scenarios = [s for s in scenarios if s['name'] == args.scenario]
        if not scenarios:
            print(f"Error: Scenario '{args.scenario}' not found")
            print("Available:", [s['name'] for s in SCENARIOS_BACKGROUND + SCENARIOS_WITH_PERSON])
            return
    elif not args.all_scenarios and not args.all_combinations:
        scenarios = scenarios[:1]  # Default: first scenario
    
    # Setup
    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    dtype = dtype_map[args.dtype]
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize pipeline
    pipeline = AdBannerPipeline(
        device=args.device,
        dtype=dtype,
        quantize=args.quantize,
    )
    
    # Generation kwargs
    gen_kwargs = {
        "headline": args.headline,
        "description": args.description,
        "phone": args.phone,
        "disclaimer": args.disclaimer,
        "layout": get_layout_by_name(args.layout) if args.layout else None,
        "style": get_style_by_name(args.style) if args.style else None,
        "width": args.width,
        "height": args.height,
        "num_inference_steps": args.steps,
        "guidance_scale": args.cfg_scale,
        "seed": args.seed,
        "add_card_bg": not args.no_card_bg,
    }
    
    # Generate
    if args.all_combinations:
        results = pipeline.generate_all_combinations(
            scenarios=scenarios,
            output_dir=output_dir,
            max_combinations=args.max_combinations,
            **gen_kwargs,
        )
    else:
        results = pipeline.generate_batch(
            scenarios=scenarios,
            output_dir=output_dir,
            variations_per_scenario=args.variations,
            **gen_kwargs,
        )
    
    # Save metadata
    if args.save_metadata:
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nMetadata saved: {metadata_path}")
    
    print(f"\n✓ Generated {len(results)} banners in {output_dir}")


if __name__ == "__main__":
    main()
