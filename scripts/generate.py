#!/usr/bin/env python3
"""
Image Generation Script

Примеры запуска:

# Простая генерация (работает из коробки с SDXL):
python scripts/generate.py --prompt "A poster with text \"Hello World\"" --simple

# С 4-bit квантизацией (~8GB VRAM вместо 24GB):
python scripts/generate.py --prompt "A poster with text \"Hello World\"" --simple --quantize 4bit

# С 8-bit квантизацией (~12GB VRAM):
python scripts/generate.py --prompt "A poster with text \"Hello World\"" --simple --quantize 8bit

# С полным пайплайном (требует обученных весов):
python scripts/generate.py --prompt "A poster with text \"Hello World\"" \
    --ar-model checkpoints/ar-model \
    --dit-model checkpoints/dit-model \
    --vq-model checkpoints/vq-model

# Множественная генерация:
python scripts/generate.py --prompt "Banner with \"SALE 50%\"" --num-images 4 --simple
"""

import argparse
import sys
from pathlib import Path
import torch
from PIL import Image

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(description="Generate images with GLM-Image")
    
    # Input
    parser.add_argument("--prompt", type=str, required=True,
                        help="Text prompt. Put text to render in quotes.")
    parser.add_argument("--negative-prompt", type=str, default="",
                        help="Negative prompt")
    
    # Mode
    parser.add_argument("--simple", action="store_true",
                        help="Use simple pipeline (SDXL, works out of box)")
    
    # Model paths (for full pipeline)
    parser.add_argument("--ar-model", type=str, default=None,
                        help="Path to AR model checkpoint")
    parser.add_argument("--dit-model", type=str, default=None,
                        help="Path to DiT model checkpoint")
    parser.add_argument("--vq-model", type=str, default=None,
                        help="Path to VQ model checkpoint")
    
    # Generation params
    parser.add_argument("--width", type=int, default=1024,
                        help="Image width (multiple of 32)")
    parser.add_argument("--height", type=int, default=1024,
                        help="Image height (multiple of 32)")
    parser.add_argument("--steps", type=int, default=50,
                        help="Number of inference steps")
    parser.add_argument("--cfg-scale", type=float, default=7.5,
                        help="CFG guidance scale")
    parser.add_argument("--temperature", type=float, default=0.9,
                        help="AR sampling temperature")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed")
    parser.add_argument("--num-images", type=int, default=1,
                        help="Number of images to generate")
    
    # Output
    parser.add_argument("--output", type=str, default="output",
                        help="Output directory")
    parser.add_argument("--format", type=str, default="png",
                        choices=["png", "jpg", "webp"],
                        help="Output format")
    
    # Device
    parser.add_argument("--device", type=str, default="cuda",
                        help="Device (cuda/cpu)")
    parser.add_argument("--dtype", type=str, default="fp16",
                        choices=["fp16", "bf16", "fp32"],
                        help="Model dtype")
    parser.add_argument("--quantize", type=str, default=None,
                        choices=["4bit", "8bit"],
                        help="Enable quantization (4bit/8bit) to reduce VRAM")
    
    args = parser.parse_args()
    
    # Setup
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True, parents=True)
    
    dtype_map = {
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
        "fp32": torch.float32,
    }
    dtype = dtype_map[args.dtype]
    
    # Create pipeline
    if args.simple:
        from pipeline.inference.simple_pipeline import SimpleImagePipeline
        
        print("Using simple pipeline (SDXL)...")
        if args.quantize:
            print(f"Quantization: {args.quantize}")
            
        pipeline = SimpleImagePipeline(
            device=args.device,
            dtype=dtype,
            quantize=args.quantize,
        )
        
        # Generate
        images = pipeline.generate(
            prompt=args.prompt,
            negative_prompt=args.negative_prompt,
            width=args.width,
            height=args.height,
            num_inference_steps=args.steps,
            guidance_scale=args.cfg_scale,
            seed=args.seed,
            num_images=args.num_images,
        )
    else:
        from pipeline.inference.pipeline import GLMImagePipeline
        
        print("Using full GLM-Image pipeline...")
        pipeline = GLMImagePipeline(
            ar_model_path=args.ar_model,
            dit_model_path=args.dit_model,
            vq_model_path=args.vq_model,
            device=args.device,
            dtype=dtype,
        )
        
        # Generate
        output = pipeline.generate(
            prompt=args.prompt,
            resolution=(args.height, args.width),
            num_inference_steps=args.steps,
            guidance_scale=args.cfg_scale,
            temperature=args.temperature,
            seed=args.seed,
        )
        images = output.images
    
    # Save images
    for i, img in enumerate(images):
        filename = f"generated_{i:04d}.{args.format}"
        filepath = output_dir / filename
        img.save(filepath)
        print(f"Saved: {filepath}")
        
    print(f"\nGenerated {len(images)} image(s) in {output_dir}/")


if __name__ == "__main__":
    main()
