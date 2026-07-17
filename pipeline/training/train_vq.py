#!/usr/bin/env python3
"""
Stage 1: VQ Encoder Training

Обучает VQ encoder сжимать изображения в дискретные семантические токены.

Запуск:
    python -m pipeline.training.train_vq \
        --config configs/vq_config.yaml \
        --data-dir data/images \
        --output-dir checkpoints/vq-encoder \
        --num-gpus 8

Что происходит:
    1. Загружаем изображения
    2. Encoder: image → continuous embeddings
    3. VQ: continuous → discrete tokens (через codebook)
    4. Decoder: tokens → reconstructed image
    5. Loss: reconstruction + commitment + perceptual
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset
from torch.cuda.amp import autocast, GradScaler
import torchvision.transforms as T
from PIL import Image
from tqdm import tqdm
import wandb
from omegaconf import OmegaConf
from typing import Optional, Dict, Any

try:
    import lpips
except ImportError as e:
    raise ImportError(
        "lpips is required for VQ training. Install: pip install lpips"
    ) from e

from models.vq_encoder import SemanticVQModel


class ImageDataset(Dataset):
    """Simple image dataset."""
    
    def __init__(
        self,
        data_dir: str,
        image_size: int = 512,
        extensions: tuple = (".jpg", ".jpeg", ".png", ".webp"),
    ):
        self.data_dir = Path(data_dir)
        self.image_size = image_size
        
        # Collect all images
        self.image_paths = []
        for ext in extensions:
            self.image_paths.extend(self.data_dir.rglob(f"*{ext}"))
            self.image_paths.extend(self.data_dir.rglob(f"*{ext.upper()}"))
            
        print(f"Found {len(self.image_paths)} images in {data_dir}")
        
        self.transform = T.Compose([
            T.Resize(image_size),
            T.CenterCrop(image_size),
            T.ToTensor(),
            T.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),  # [-1, 1]
        ])
        
    def __len__(self):
        return len(self.image_paths)
    
    def __getitem__(self, idx):
        img_path = self.image_paths[idx]
        try:
            img = Image.open(img_path).convert("RGB")
            return self.transform(img)
        except Exception as e:
            # Return random noise if image is corrupted
            return torch.randn(3, self.image_size, self.image_size)


class VQTrainer:
    """
    VQ Encoder Trainer.
    
    Training loop:
        1. Forward: image → encoder → VQ → decoder → reconstruction
        2. Losses: MSE + commitment + perceptual + adversarial
        3. Backward + optimizer step
        4. EMA update codebook
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        output_dir: str,
        device: str = "cuda",
    ):
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.device = device
        
        # Model
        self.model = self._build_model()
        
        # Perceptual loss (LPIPS)
        self.perceptual_loss = lpips.LPIPS(net='vgg').to(device)
        self.perceptual_loss.eval()
        
        # Optimizer
        self.optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=config.get("lr", 1e-4),
            betas=(0.9, 0.99),
            weight_decay=config.get("weight_decay", 0.01),
        )
        
        # Scheduler
        self.scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
            self.optimizer,
            T_max=config.get("num_epochs", 100),
            eta_min=1e-6,
        )
        
        # Mixed precision
        self.scaler = GradScaler()
        
        # Logging
        self.global_step = 0
        
    def _build_model(self) -> SemanticVQModel:
        """Build VQ model from config."""
        model_config = self.config.get("model", {})
        model = SemanticVQModel(
            encoder_type=model_config.get("encoder_type", "vit"),
            backbone=model_config.get("backbone", "vit_large_patch16_384"),
            num_embeddings=model_config.get("num_embeddings", 16384),
            embedding_dim=model_config.get("embedding_dim", 1024),
            commitment_cost=model_config.get("commitment_cost", 0.25),
        )
        return model.to(self.device)
    
    def train_epoch(self, dataloader: DataLoader, epoch: int) -> Dict[str, float]:
        """Train one epoch."""
        self.model.train()
        
        total_loss = 0
        total_recon = 0
        total_commit = 0
        total_perceptual = 0
        num_batches = 0
        
        pbar = tqdm(dataloader, desc=f"Epoch {epoch}")
        
        for batch in pbar:
            images = batch.to(self.device)
            
            # Forward with mixed precision
            with autocast():
                reconstructed, indices, losses = self.model(images)
                
                # Perceptual loss
                perceptual = self.perceptual_loss(reconstructed, images).mean()
                
                # Total loss
                loss = (
                    losses["reconstruction"] * self.config.get("recon_weight", 1.0) +
                    losses["commitment"] * self.config.get("commit_weight", 0.25) +
                    perceptual * self.config.get("perceptual_weight", 0.1)
                )
                
            # Backward
            self.optimizer.zero_grad()
            self.scaler.scale(loss).backward()
            self.scaler.unscale_(self.optimizer)
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.scaler.step(self.optimizer)
            self.scaler.update()
            
            # Logging
            total_loss += loss.item()
            total_recon += losses["reconstruction"].item()
            total_commit += losses["commitment"].item()
            total_perceptual += perceptual.item()
            num_batches += 1
            
            pbar.set_postfix({
                "loss": f"{loss.item():.4f}",
                "recon": f"{losses['reconstruction'].item():.4f}",
                "pplx": f"{losses.get('perplexity', 0):.1f}",
            })
            
            self.global_step += 1
            
            # Log to wandb
            if self.global_step % 100 == 0:
                wandb.log({
                    "train/loss": loss.item(),
                    "train/reconstruction": losses["reconstruction"].item(),
                    "train/commitment": losses["commitment"].item(),
                    "train/perceptual": perceptual.item(),
                    "train/perplexity": losses.get("perplexity", 0),
                    "train/utilization": losses.get("utilization", 0),
                    "train/lr": self.optimizer.param_groups[0]["lr"],
                }, step=self.global_step)
                
        return {
            "loss": total_loss / num_batches,
            "reconstruction": total_recon / num_batches,
            "commitment": total_commit / num_batches,
            "perceptual": total_perceptual / num_batches,
        }
    
    @torch.no_grad()
    def validate(self, dataloader: DataLoader) -> Dict[str, float]:
        """Validate model."""
        self.model.eval()
        
        total_recon = 0
        num_batches = 0
        
        for batch in tqdm(dataloader, desc="Validation"):
            images = batch.to(self.device)
            reconstructed, indices, losses = self.model(images)
            total_recon += losses["reconstruction"].item()
            num_batches += 1
            
        return {"val_reconstruction": total_recon / num_batches}
    
    def save_checkpoint(self, epoch: int, metrics: Dict[str, float]):
        """Save checkpoint."""
        checkpoint = {
            "epoch": epoch,
            "model": self.model.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "scheduler": self.scheduler.state_dict(),
            "config": self.config,
            "metrics": metrics,
        }
        
        path = self.output_dir / f"checkpoint_epoch_{epoch}.pt"
        torch.save(checkpoint, path)
        
        # Also save best
        best_path = self.output_dir / "best.pt"
        torch.save(checkpoint, best_path)
        
        print(f"Saved checkpoint to {path}")
        
    def train(
        self,
        train_dataloader: DataLoader,
        val_dataloader: Optional[DataLoader] = None,
        num_epochs: int = 100,
    ):
        """Full training loop."""
        print(f"Starting VQ training for {num_epochs} epochs")
        print(f"Output dir: {self.output_dir}")
        
        best_loss = float("inf")
        
        for epoch in range(num_epochs):
            # Train
            train_metrics = self.train_epoch(train_dataloader, epoch)
            print(f"Epoch {epoch}: {train_metrics}")
            
            # Validate
            if val_dataloader is not None:
                val_metrics = self.validate(val_dataloader)
                print(f"Validation: {val_metrics}")
                wandb.log(val_metrics, step=self.global_step)
                
            # LR schedule
            self.scheduler.step()
            
            # Save checkpoint
            if train_metrics["loss"] < best_loss:
                best_loss = train_metrics["loss"]
                self.save_checkpoint(epoch, train_metrics)
                
            # Reset unused codes periodically
            if epoch % 10 == 0:
                self.model.codebook.reset_unused()


def main():
    parser = argparse.ArgumentParser(description="Train VQ Encoder")
    parser.add_argument("--config", type=str, default="configs/vq_config.yaml")
    parser.add_argument("--data-dir", type=str, required=True)
    parser.add_argument("--output-dir", type=str, default="checkpoints/vq-encoder")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--num-epochs", type=int, default=100)
    parser.add_argument("--num-workers", type=int, default=8)
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--num-gpus", type=int, default=1)
    parser.add_argument("--wandb-project", type=str, default="glm-image-vq")
    
    args = parser.parse_args()
    
    # Load config
    config = OmegaConf.load(args.config)
    config = OmegaConf.to_container(config, resolve=True)
    config["batch_size"] = args.batch_size
    config["num_epochs"] = args.num_epochs
    
    # Init wandb
    wandb.init(project=args.wandb_project, config=config)
    
    # Dataset
    train_dataset = ImageDataset(args.data_dir, image_size=args.image_size)
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=True,
        drop_last=True,
    )
    
    # Trainer
    trainer = VQTrainer(config, args.output_dir)
    
    # Train
    trainer.train(train_loader, num_epochs=args.num_epochs)
    
    print("VQ training complete!")


if __name__ == "__main__":
    main()
