#!/usr/bin/env python3
"""
Banner Generation Script

Генерация баннеров с поддержкой сценариев, лейаутов и стилей.

Примеры запуска:

# Из JSON конфига:
python scripts/generate_banners.py --config configs/banners.json --output output/banners

# Конкретный сценарий:
python scripts/generate_banners.py --scenario courthouse --output output/banners

# Все сценарии:
python scripts/generate_banners.py --all-scenarios --output output/banners

# С квантизацией:
python scripts/generate_banners.py --config configs/banners.json --quantize 4bit

# Конкретный промпт из списка:
python scripts/generate_banners.py --scenario-index 0 --output output/banners
"""

import argparse
import sys
from pathlib import Path
import json
import torch
from PIL import Image
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import random

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import text overlay (optional, loaded on demand)
TEXT_OVERLAY_AVAILABLE = False
try:
    from scripts.text_overlay import (
        BannerOverlay,
        LAYOUTS as TEXT_LAYOUTS,
        TEXT_STYLES,
        DEFAULT_HEADLINES,
        DEFAULT_DESCRIPTIONS,
        DEFAULT_DISCLAIMERS,
        generate_phone,
        get_layout_by_name,
        get_style_by_name,
    )
    TEXT_OVERLAY_AVAILABLE = True
except ImportError:
    pass


# =============================================================================
# Default Configurations
# =============================================================================

SCENARIOS_BACKGROUND = [
    {
        "name": "courthouse",
        "prompt": "professional legal advertisement background, grand courthouse interior marble columns, golden scales of justice, deep navy blue burgundy, soft ambient lighting, elegant empty space, 8k quality, no people, no person",
    },
    {
        "name": "office_empty",
        "prompt": "modern law firm office interior background, sleek glass steel, leather chairs, law books shelves, city skyline window, navy gold accents, professional empty office, no people",
    },
    {
        "name": "abstract_legal",
        "prompt": "abstract professional legal background, geometric dark blue gold patterns, subtle scales of justice, elegant gradient, minimalist corporate design, empty clean, no people",
    },
    {
        "name": "library",
        "prompt": "elegant law library background, antique wooden bookshelves, leather legal volumes, brass lamp, warm golden lighting, mahogany burgundy, classic professional, no people",
    },
    {
        "name": "justice_symbols",
        "prompt": "professional legal background, prominent golden scales of justice, marble texture, deep blue, laurel wreath elements, classical columns, authoritative, no people",
    },
]

SCENARIOS_WITH_PERSON = [
    {
        "name": "lawyer_portrait_right",
        "prompt": "professional lawyer portrait photo, confident businessman in dark suit, standing on right side of frame, modern office background, soft lighting, corporate style, space for text on left, high quality portrait",
        "person_side": "right"
    },
    {
        "name": "lawyer_portrait_left",
        "prompt": "professional female lawyer portrait, confident businesswoman in elegant suit, standing on left side of frame, law office with books background, professional lighting, space for text on right, corporate photo",
        "person_side": "left"
    },
    {
        "name": "lawyer_desk",
        "prompt": "professional lawyer sitting at desk, businessman in suit, office interior, law books behind, looking at camera, confident pose, bottom half of frame, space for text at top, corporate portrait",
        "person_side": "bottom"
    },
]

LAYOUTS = [
    {
        "name": "classic_left",
        "headline": {"x": 40, "y": 80, "max_w": 500, "align": "left"},
        "description": {"x": 40, "y": 400, "max_w": 450, "align": "left"},
        "phone": {"x": 40, "y": 700, "align": "left"},
        "disclaimer": {"x": 40, "y": 950, "max_w": 600, "align": "left"},
        "card_zone": {"x": 25, "y": 60, "w": 530, "h": 750}
    },
    {
        "name": "classic_right",
        "headline": {"x": 524, "y": 80, "max_w": 460, "align": "left"},
        "description": {"x": 524, "y": 400, "max_w": 450, "align": "left"},
        "phone": {"x": 524, "y": 700, "align": "left"},
        "disclaimer": {"x": 524, "y": 950, "max_w": 460, "align": "left"},
        "card_zone": {"x": 504, "y": 60, "w": 500, "h": 750}
    },
    {
        "name": "top_bottom",
        "headline": {"x": 512, "y": 60, "max_w": 900, "align": "center"},
        "description": {"x": 512, "y": 750, "max_w": 800, "align": "center"},
        "phone": {"x": 512, "y": 870, "align": "center"},
        "disclaimer": {"x": 512, "y": 970, "max_w": 700, "align": "center"},
        "card_zone": None
    },
    {
        "name": "diagonal",
        "headline": {"x": 60, "y": 60, "max_w": 550, "align": "left"},
        "description": {"x": 474, "y": 500, "max_w": 500, "align": "left"},
        "phone": {"x": 474, "y": 750, "align": "left"},
        "disclaimer": {"x": 60, "y": 970, "max_w": 600, "align": "left"},
        "card_zone": None
    },
    {
        "name": "center_stack",
        "headline": {"x": 512, "y": 150, "max_w": 800, "align": "center"},
        "description": {"x": 512, "y": 450, "max_w": 700, "align": "center"},
        "phone": {"x": 512, "y": 650, "align": "center"},
        "disclaimer": {"x": 512, "y": 920, "max_w": 600, "align": "center"},
        "card_zone": {"x": 100, "y": 120, "w": 824, "h": 600}
    },
]

TEXT_STYLES = [
    {"name": "gold", "headline_color": (255, 215, 100), "text_color": (255, 255, 255), "accent_color": (212, 175, 55)},
    {"name": "white", "headline_color": (255, 255, 255), "text_color": (240, 240, 240), "accent_color": (255, 255, 255)},
    {"name": "cream", "headline_color": (255, 248, 220), "text_color": (250, 250, 245), "accent_color": (230, 220, 180)},
    {"name": "silver", "headline_color": (220, 220, 230), "text_color": (240, 240, 245), "accent_color": (180, 180, 195)},
    {"name": "bronze", "headline_color": (205, 150, 80), "text_color": (255, 255, 255), "accent_color": (180, 130, 70)},
]

NEG_PROMPT = "text, words, letters, watermark, logo, cartoon, anime, 3d render, cluttered, bright neon colors, low quality, blurry, deformed"
NEG_PROMPT_PERSON = "deformed, ugly, bad anatomy, extra limbs, blurry, low quality, cartoon, anime, watermark, text"


# =============================================================================
# Banner Generator
# =============================================================================

class BannerGenerator:
    """
    Генератор баннеров с поддержкой сценариев и лейаутов.
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
        """Load pipeline."""
        if self._pipeline is not None:
            return
            
        from pipeline.inference.simple_pipeline import SimpleImagePipeline
        
        print(f"Loading pipeline...")
        self._pipeline = SimpleImagePipeline(
            model_id=self.model_id,
            device=self.device,
            dtype=self.dtype,
            quantize=self.quantize,
        )
        self._pipeline.load()
        
    def generate_from_scenario(
        self,
        scenario: Dict[str, Any],
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
        negative_prompt: Optional[str] = None,
        with_text: bool = False,
        headline: str = None,
        description: str = None,
        phone: str = None,
        disclaimer: str = None,
        layout_name: str = None,
        text_style_name: str = None,
    ) -> Image.Image:
        """
        Generate image from scenario config.
        
        Args:
            scenario: Dict with 'name' and 'prompt' keys
            width, height: Image dimensions
            num_inference_steps: Diffusion steps
            guidance_scale: CFG scale
            seed: Random seed
            negative_prompt: Override negative prompt
            with_text: Add text overlay
            headline, description, phone, disclaimer: Text content
            layout_name: Layout for text
            text_style_name: Style for text
            
        Returns:
            PIL Image
        """
        self.load()
        
        prompt = scenario["prompt"]
        
        # Determine negative prompt
        if negative_prompt is None:
            if "person_side" in scenario:
                negative_prompt = NEG_PROMPT_PERSON
            else:
                negative_prompt = NEG_PROMPT
                
        images = self._pipeline.generate(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            num_images=1,
        )
        
        image = images[0]
        
        # Apply text overlay if requested
        if with_text and TEXT_OVERLAY_AVAILABLE:
            image = self._apply_text_overlay(
                image, scenario,
                headline=headline,
                description=description,
                phone=phone,
                disclaimer=disclaimer,
                layout_name=layout_name,
                text_style_name=text_style_name,
            )
        
        return image
    
    def _apply_text_overlay(
        self,
        image: Image.Image,
        scenario: Dict[str, Any],
        headline: str = None,
        description: str = None,
        phone: str = None,
        disclaimer: str = None,
        layout_name: str = None,
        text_style_name: str = None,
    ) -> Image.Image:
        """Apply text overlay to image."""
        if not TEXT_OVERLAY_AVAILABLE:
            print("Warning: text_overlay module not available")
            return image
        
        # Select layout based on scenario
        if layout_name:
            layout = get_layout_by_name(layout_name)
        else:
            layout = self._select_layout_for_scenario(scenario)
        
        # Select style
        style = get_style_by_name(text_style_name) if text_style_name else random.choice(TEXT_STYLES)
        
        # Get text content
        headline = headline or random.choice(DEFAULT_HEADLINES)
        description = description or random.choice(DEFAULT_DESCRIPTIONS)
        phone = phone or generate_phone()
        disclaimer = disclaimer or random.choice(DEFAULT_DISCLAIMERS)
        
        # Apply overlay
        overlay = BannerOverlay(layout=layout, style=style)
        return overlay.apply(
            image,
            headline=headline,
            description=description,
            phone=phone,
            disclaimer=disclaimer,
            add_card_bg=True,
        )
    
    def _select_layout_for_scenario(self, scenario: Dict) -> Dict:
        """Select appropriate layout based on scenario."""
        if not TEXT_OVERLAY_AVAILABLE:
            return {}
        
        if 'person_side' in scenario:
            side = scenario['person_side']
            if side == "right":
                candidates = [l for l in TEXT_LAYOUTS if l['name'] in ['classic_left', 'diagonal']]
            elif side == "left":
                candidates = [l for l in TEXT_LAYOUTS if l['name'] in ['classic_right']]
            elif side == "bottom":
                candidates = [l for l in TEXT_LAYOUTS if l['name'] in ['top_bottom', 'center_stack']]
            else:
                candidates = TEXT_LAYOUTS
        else:
            candidates = TEXT_LAYOUTS
        
        return random.choice(candidates) if candidates else random.choice(TEXT_LAYOUTS)
    
    def generate_batch(
        self,
        scenarios: List[Dict[str, Any]],
        output_dir: Path,
        with_text: bool = False,
        headline: str = None,
        description: str = None,
        phone: str = None,
        disclaimer: str = None,
        layout_name: str = None,
        text_style_name: str = None,
        **kwargs,
    ) -> List[Path]:
        """
        Generate images for multiple scenarios.
        
        Returns list of saved file paths.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        saved_paths = []
        
        for i, scenario in enumerate(scenarios):
            print(f"\n[{i+1}/{len(scenarios)}] Generating: {scenario['name']}")
            
            image = self.generate_from_scenario(
                scenario,
                with_text=with_text,
                headline=headline,
                description=description,
                phone=phone,
                disclaimer=disclaimer,
                layout_name=layout_name,
                text_style_name=text_style_name,
                **kwargs
            )
            
            # Save
            suffix = "_with_text" if with_text else ""
            filename = f"{scenario['name']}{suffix}_{i:04d}.png"
            filepath = output_dir / filename
            image.save(filepath)
            saved_paths.append(filepath)
            
            print(f"Saved: {filepath}")
            
        return saved_paths
    
    def generate_all_combinations(
        self,
        scenarios: List[Dict],
        layouts: List[Dict],
        styles: List[Dict],
        output_dir: Path,
        max_combinations: int = None,
        **kwargs,
    ) -> List[Dict]:
        """
        Generate all combinations of scenarios, layouts, and styles.
        
        Returns metadata for each generated image.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        count = 0
        
        for scenario in scenarios:
            for layout in layouts:
                for style in styles:
                    if max_combinations and count >= max_combinations:
                        return results
                        
                    name = f"{scenario['name']}_{layout['name']}_{style['name']}"
                    print(f"\n[{count+1}] Generating: {name}")
                    
                    image = self.generate_from_scenario(scenario, **kwargs)
                    
                    # Save image
                    filepath = output_dir / f"{name}.png"
                    image.save(filepath)
                    
                    # Save metadata
                    result = {
                        "filename": str(filepath),
                        "scenario": scenario,
                        "layout": layout,
                        "style": style,
                    }
                    results.append(result)
                    count += 1
                    
        return results


def load_config(config_path: str) -> Dict:
    """Load configuration from JSON file."""
    with open(config_path) as f:
        return json.load(f)


def save_default_config(output_path: str):
    """Save default configuration to JSON file."""
    config = {
        "scenarios_background": SCENARIOS_BACKGROUND,
        "scenarios_with_person": SCENARIOS_WITH_PERSON,
        "layouts": LAYOUTS,
        "text_styles": TEXT_STYLES,
        "negative_prompt": NEG_PROMPT,
        "negative_prompt_person": NEG_PROMPT_PERSON,
        "generation": {
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 50,
            "guidance_scale": 7.5,
        }
    }
    
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        
    print(f"Default config saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate banners with scenarios")
    
    # Input
    parser.add_argument("--config", type=str, default=None,
                        help="Path to JSON config file")
    parser.add_argument("--scenario", type=str, default=None,
                        help="Specific scenario name to generate")
    parser.add_argument("--scenario-index", type=int, default=None,
                        help="Scenario index (0-based)")
    parser.add_argument("--all-scenarios", action="store_true",
                        help="Generate all built-in scenarios")
    parser.add_argument("--all-combinations", action="store_true",
                        help="Generate all scenario+layout+style combinations")
    parser.add_argument("--max-combinations", type=int, default=None,
                        help="Limit number of combinations")
    
    # Text overlay options
    parser.add_argument("--with-text", action="store_true",
                        help="Add text overlay to generated images")
    parser.add_argument("--headline", type=str, help="Custom headline text")
    parser.add_argument("--description", type=str, help="Custom description text")
    parser.add_argument("--phone", type=str, help="Custom phone number")
    parser.add_argument("--layout", type=str, help="Layout name for text")
    parser.add_argument("--text-style", type=str, help="Text style name")
    
    # Generation params
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--cfg-scale", type=float, default=7.5)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--negative-prompt", type=str, default=None)
    
    # Output
    parser.add_argument("--output", type=str, default="output/banners",
                        help="Output directory")
    parser.add_argument("--save-metadata", action="store_true",
                        help="Save generation metadata to JSON")
    
    # Model
    parser.add_argument("--quantize", type=str, default=None,
                        choices=["4bit", "8bit"],
                        help="Enable quantization")
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--dtype", type=str, default="fp16",
                        choices=["fp16", "bf16", "fp32"])
    
    # Utilities
    parser.add_argument("--save-default-config", type=str, default=None,
                        help="Save default config to JSON and exit")
    parser.add_argument("--list-scenarios", action="store_true",
                        help="List available scenarios and exit")
    
    args = parser.parse_args()
    
    # Utility actions
    if args.save_default_config:
        save_default_config(args.save_default_config)
        return
        
    if args.list_scenarios:
        print("\n=== Background Scenarios ===")
        for i, s in enumerate(SCENARIOS_BACKGROUND):
            print(f"  [{i}] {s['name']}")
        print("\n=== Person Scenarios ===")
        for i, s in enumerate(SCENARIOS_WITH_PERSON):
            print(f"  [{i}] {s['name']} (person_side: {s.get('person_side', 'N/A')})")
        print("\n=== Layouts ===")
        for l in LAYOUTS:
            print(f"  - {l['name']}")
        print("\n=== Text Styles ===")
        for s in TEXT_STYLES:
            print(f"  - {s['name']}")
        return
    
    # Setup
    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    dtype = dtype_map[args.dtype]
    
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load config or use defaults
    if args.config:
        config = load_config(args.config)
        scenarios = config.get("scenarios_background", SCENARIOS_BACKGROUND)
        scenarios += config.get("scenarios_with_person", SCENARIOS_WITH_PERSON)
    else:
        scenarios = SCENARIOS_BACKGROUND + SCENARIOS_WITH_PERSON
        
    # Filter scenarios
    if args.scenario:
        scenarios = [s for s in scenarios if s["name"] == args.scenario]
        if not scenarios:
            print(f"Scenario '{args.scenario}' not found!")
            print("Use --list-scenarios to see available scenarios")
            return
    elif args.scenario_index is not None:
        if 0 <= args.scenario_index < len(scenarios):
            scenarios = [scenarios[args.scenario_index]]
        else:
            print(f"Invalid scenario index: {args.scenario_index}")
            return
    elif not args.all_scenarios and not args.all_combinations:
        # Default: first scenario only
        scenarios = scenarios[:1]
        
    # Initialize generator
    generator = BannerGenerator(
        device=args.device,
        dtype=dtype,
        quantize=args.quantize,
    )
    
    # Generation kwargs
    gen_kwargs = {
        "width": args.width,
        "height": args.height,
        "num_inference_steps": args.steps,
        "guidance_scale": args.cfg_scale,
        "seed": args.seed,
        "negative_prompt": args.negative_prompt,
        "with_text": args.with_text,
        "headline": args.headline,
        "description": args.description,
        "phone": args.phone,
        "layout_name": args.layout,
        "text_style_name": args.text_style,
    }
    
    # Generate
    if args.all_combinations:
        results = generator.generate_all_combinations(
            scenarios=scenarios,
            layouts=LAYOUTS,
            styles=TEXT_STYLES,
            output_dir=output_dir,
            max_combinations=args.max_combinations,
            **gen_kwargs,
        )
        
        if args.save_metadata:
            metadata_path = output_dir / "metadata.json"
            with open(metadata_path, "w") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\nMetadata saved to: {metadata_path}")
    else:
        paths = generator.generate_batch(
            scenarios=scenarios,
            output_dir=output_dir,
            **gen_kwargs,
        )
        
    print(f"\nGeneration complete! Output: {output_dir}")


if __name__ == "__main__":
    main()
