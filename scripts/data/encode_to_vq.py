#!/usr/bin/env python3
"""
Encode images to VQ tokens for AR training.

Запуск:
    python scripts/data/encode_to_vq.py \
        --vq-checkpoint checkpoints/vq-encoder/best.pt \
        --images-dir data/images \
        --captions data/captions.json \
        --output data/vq-tokens \
        --num-workers 32

Формат выхода:
    data/vq-tokens/
    ├── 00000.pt  # {"text": "...", "vq_tokens": [1234, 5678, ...]}
    └── ...
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
import torch
from torch.utils.data import DataLoader, Dataset
import torchvision.transforms as T
from PIL import Image
from tqdm import tqdm
import json
from typing import Dict, List, Optional
import multiprocessing as mp

from models.vq_encoder import SemanticVQModel


class ImageCaptionDataset(Dataset):
    """Dataset with images and captions."""
    
    def __init__(
        self,
        images_dir: str,
        captions_file: Optional[str] = None,
        image_size: int = 1024,
    ):
        self.images_dir = Path(images_dir)
        self.image_size = image_size
        
        # Collect images
        self.image_files = []
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            self.image_files.extend(self.images_dir.rglob(f"*{ext}"))
            self.image_files.extend(self.images_dir.rglob(f"*{ext.upper()}"))
            
        self.image_files = sorted(self.image_files)
        
        # Load captions
        self.captions = {}
        if captions_file and Path(captions_file).exists():
            with open(captions_file) as f:
                data = json.load(f)
                
            # Support multiple formats
            if isinstance(data, list):
                for item in data:
                    filename = item.get("file_name", item.get("image", ""))
                    caption = item.get("caption", item.get("text", ""))
                    self.captions[filename] = caption
            elif isinstance(data, dict):
                self.captions = data
                
        print(f"Found {len(self.image_files)} images, {len(self.captions)} captions")
        
        self.transform = T.Compose([
            T.Resize(image_size),
            T.CenterCrop(image_size),
            T.ToTensor(),
            T.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
        ])
        
    def __len__(self):
        return len(self.image_files)
    
    def __getitem__(self, idx):
        img_path = self.image_files[idx]
        
        try:
            img = Image.open(img_path).convert("RGB")
            img_tensor = self.transform(img)
        except Exception as e:
            print(f"Error loading {img_path}: {e}")
            img_tensor = torch.zeros(3, self.image_size, self.image_size)
            
        # Get caption
        filename = img_path.name
        caption = self.captions.get(filename, "")
        
        if not caption:
            # Try without extension
            stem = img_path.stem
            caption = self.captions.get(stem, f"An image of {stem}")
            
        return {
            "image": img_tensor,
            "caption": caption,
            "filename": filename,
            "idx": idx,
        }


def encode_batch(
    vq_model: SemanticVQModel,
    images: torch.Tensor,
    device: str = "cuda",
) -> torch.Tensor:
    """Encode batch of images to VQ tokens."""
    with torch.no_grad():
        images = images.to(device)
        indices, _ = vq_model.encode(images)
        return indices.cpu()


def main():
    parser = argparse.ArgumentParser(description="Encode images to VQ tokens")
    parser.add_argument("--vq-checkpoint", type=str, required=True)
    parser.add_argument("--images-dir", type=str, required=True)
    parser.add_argument("--captions", type=str, default=None)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--num-workers", type=int, default=8)
    parser.add_argument("--image-size", type=int, default=1024)
    
    args = parser.parse_args()
    
    # Create output dir
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load VQ model
    print(f"Loading VQ model from {args.vq_checkpoint}...")
    checkpoint = torch.load(args.vq_checkpoint, map_location="cpu")
    
    vq_model = SemanticVQModel(**checkpoint.get("config", {}))
    vq_model.load_state_dict(checkpoint["model"])
    vq_model = vq_model.cuda()
    vq_model.eval()
    
    # Dataset
    dataset = ImageCaptionDataset(
        args.images_dir,
        args.captions,
        image_size=args.image_size,
    )
    
    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True,
    )
    
    # Process
    print(f"Encoding {len(dataset)} images...")
    
    for batch in tqdm(dataloader):
        images = batch["image"]
        captions = batch["caption"]
        filenames = batch["filename"]
        indices = batch["idx"]
        
        # Encode
        vq_tokens = encode_batch(vq_model, images)
        
        # Save each sample
        for i in range(len(indices)):
            idx = indices[i].item()
            
            sample = {
                "text": captions[i],
                "vq_tokens": vq_tokens[i].flatten().tolist(),
                "filename": filenames[i],
                "grid_size": list(vq_tokens[i].shape),
            }
            
            output_path = output_dir / f"{idx:08d}.pt"
            torch.save(sample, output_path)
            
    print(f"Done! Saved {len(dataset)} samples to {output_dir}")


if __name__ == "__main__":
    main()
