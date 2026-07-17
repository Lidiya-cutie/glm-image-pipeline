#!/usr/bin/env python3
"""
Stage 3: DiT Decoder Training

Обучает DiT decoder генерировать изображения по VQ токенам и тексту.

Запуск:
    python -m pipeline.training.train_dit \
        --config configs/training_config.yaml \
        --vq-checkpoint checkpoints/vq-encoder/best.pt \
        --data-dir data/dit-training \
        --output-dir checkpoints/dit-model

Формат данных:
    data/dit-training/
    ├── 00000.pt  # {"image": tensor, "vq_tokens": tensor, "text_embed": tensor}
    └── ...

Что происходит:
    1. Загружаем изображение → VAE → latent
    2. Добавляем шум (flow matching)
    3. DiT предсказывает velocity/noise условно на VQ + text
    4. Loss: MSE между predicted и target velocity
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
from typing import Optional, Dict, Any, Tuple
import numpy as np
from copy import deepcopy

from diffusers import AutoencoderKL
from models.dit_decoder import DiTDecoder, DiTConfig
from models.vq_encoder import SemanticVQModel


class DiTDataset(Dataset):
    """
    Dataset для DiT training.
    
    Каждый sample содержит:
    - image: RGB изображение
    - vq_tokens: VQ токены этого изображения
    - text/text_embed: текстовое описание или его embedding
    """
    
    def __init__(
        self,
        data_dir: str,
        vq_model: SemanticVQModel,
        vae: AutoencoderKL,
        image_size: int = 1024,
        latent_size: int = 128,  # 1024 / 8
    ):
        self.data_dir = Path(data_dir)
        self.vq_model = vq_model
        self.vae = vae
        self.image_size = image_size
        self.latent_size = latent_size
        
        # Collect files
        self.data_files = sorted(self.data_dir.glob("*.pt"))
        if not self.data_files:
            # Fallback: look for images + captions
            self.image_files = sorted(self.data_dir.glob("*.jpg"))
            self.data_files = None
            
        print(f"Found {len(self.data_files or self.image_files)} samples")
        
        self.transform = T.Compose([
            T.Resize(image_size),
            T.CenterCrop(image_size),
            T.ToTensor(),
            T.Normalize([0.5], [0.5]),
        ])
        
    def __len__(self):
        if self.data_files:
            return len(self.data_files)
        return len(self.image_files)
    
    @torch.no_grad()
    def __getitem__(self, idx):
        if self.data_files:
            # Pre-processed data
            data = torch.load(self.data_files[idx])
            return {
                "latent": data["latent"],  # [C, H, W] VAE latent
                "vq_embeddings": data["vq_embeddings"],  # [N, D]
                "text_embeddings": data["text_embeddings"],  # [L, D]
            }
        else:
            # Process on-the-fly (slower but more flexible)
            img_path = self.image_files[idx]
            img = Image.open(img_path).convert("RGB")
            img_tensor = self.transform(img).unsqueeze(0)
            
            # Get VAE latent
            latent = self.vae.encode(img_tensor).latent_dist.sample()
            latent = latent * self.vae.config.scaling_factor
            
            # Get VQ tokens and embeddings
            vq_indices, vq_embeddings = self.vq_model.encode(img_tensor, return_embeddings=True)
            
            return {
                "latent": latent.squeeze(0),
                "vq_embeddings": vq_embeddings.squeeze(0).view(-1, vq_embeddings.shape[-1]),
                "text_embeddings": torch.zeros(77, 4096),  # Placeholder
            }


class DiTTrainer:
    """
    DiT Decoder Trainer.
    
    Uses Flow Matching objective:
        - Sample t ~ U[0,1]
        - x_t = t * x_1 + (1-t) * x_0, where x_0 ~ N(0,1), x_1 = data
        - Target velocity: v = x_1 - x_0
        - Loss: ||model(x_t, t, cond) - v||^2
    """
    
    def __init__(
        self,
        model: DiTDecoder,
        vae: AutoencoderKL,
        config: Dict[str, Any],
        output_dir: str,
        device: str = "cuda",
    ):
        self.model = model
        self.vae = vae
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.device = device
        
        # Optimizer
        self.optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.get("lr", 1e-4),
            betas=(0.9, 0.999),
            weight_decay=config.get("weight_decay", 0.01),
        )
        
        # EMA model
        self.ema_model = deepcopy(model)
        self.ema_decay = config.get("ema_decay", 0.9999)
        
        # Mixed precision
        self.scaler = GradScaler()
        
        self.global_step = 0
        
    @torch.no_grad()
    def update_ema(self):
        """Update EMA model."""
        for ema_param, param in zip(self.ema_model.parameters(), self.model.parameters()):
            ema_param.data.mul_(self.ema_decay).add_(param.data, alpha=1 - self.ema_decay)
            
    def train_step(self, batch: Dict[str, torch.Tensor]) -> Dict[str, float]:
        """Single training step with flow matching."""
        self.model.train()
        
        latent = batch["latent"].to(self.device)  # [B, C, H, W]
        vq_embeddings = batch["vq_embeddings"].to(self.device)  # [B, N, D]
        text_embeddings = batch["text_embeddings"].to(self.device)  # [B, L, D]
        
        B = latent.shape[0]
        
        with autocast():
            # Sample timestep
            t = torch.rand(B, device=self.device)
            
            # Sample noise
            noise = torch.randn_like(latent)
            
            # Interpolate (flow matching)
            x_t = t.view(-1, 1, 1, 1) * latent + (1 - t.view(-1, 1, 1, 1)) * noise
            
            # Target velocity
            target_v = latent - noise
            
            # Predict velocity
            pred_v = self.model(x_t, t, vq_embeddings, text_embeddings)
            
            # Loss
            loss = F.mse_loss(pred_v, target_v)
            
        # Backward
        self.optimizer.zero_grad()
        self.scaler.scale(loss).backward()
        self.scaler.unscale_(self.optimizer)
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.scaler.step(self.optimizer)
        self.scaler.update()
        
        # EMA update
        self.update_ema()
        
        self.global_step += 1
        
        return {"loss": loss.item()}
    
    def train_epoch(self, dataloader: DataLoader, epoch: int) -> Dict[str, float]:
        """Train one epoch."""
        total_loss = 0
        num_batches = 0
        
        pbar = tqdm(dataloader, desc=f"Epoch {epoch}")
        for batch in pbar:
            metrics = self.train_step(batch)
            total_loss += metrics["loss"]
            num_batches += 1
            
            pbar.set_postfix({"loss": f"{metrics['loss']:.4f}"})
            
            if self.global_step % 100 == 0:
                wandb.log({
                    "train/loss": metrics["loss"],
                    "train/lr": self.optimizer.param_groups[0]["lr"],
                }, step=self.global_step)
                
        return {"loss": total_loss / num_batches}
    
    @torch.no_grad()
    def generate_sample(
        self,
        vq_embeddings: torch.Tensor,
        text_embeddings: torch.Tensor,
        latent_size: Tuple[int, int] = (128, 128),
        num_steps: int = 50,
    ) -> torch.Tensor:
        """Generate sample image for validation."""
        self.ema_model.eval()
        
        B = vq_embeddings.shape[0]
        H, W = latent_size
        
        # Start from noise
        x = torch.randn(B, 4, H, W, device=self.device)
        
        # Euler sampling
        timesteps = torch.linspace(1, 0, num_steps + 1, device=self.device)
        
        for i in range(num_steps):
            t = timesteps[i].expand(B)
            t_next = timesteps[i + 1]
            
            v = self.ema_model(x, t, vq_embeddings, text_embeddings)
            dt = t_next - t
            x = x + v * dt.view(-1, 1, 1, 1)
            
        # Decode with VAE
        x = x / self.vae.config.scaling_factor
        images = self.vae.decode(x).sample
        
        return (images / 2 + 0.5).clamp(0, 1)
    
    def save_checkpoint(self, epoch: int, metrics: Dict[str, float]):
        """Save checkpoint."""
        checkpoint = {
            "epoch": epoch,
            "model": self.model.state_dict(),
            "ema_model": self.ema_model.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "config": dict(self.model.config),
            "metrics": metrics,
        }
        
        path = self.output_dir / f"checkpoint_epoch_{epoch}.pt"
        torch.save(checkpoint, path)
        
        best_path = self.output_dir / "best.pt"
        torch.save(checkpoint, best_path)
        
        print(f"Saved checkpoint to {path}")
        
    def train(self, dataloader: DataLoader, num_epochs: int):
        """Full training loop."""
        print(f"Starting DiT training for {num_epochs} epochs")
        
        for epoch in range(num_epochs):
            metrics = self.train_epoch(dataloader, epoch)
            print(f"Epoch {epoch}: {metrics}")
            
            # Save every 5 epochs
            if (epoch + 1) % 5 == 0:
                self.save_checkpoint(epoch, metrics)


def main():
    parser = argparse.ArgumentParser(description="Train DiT Decoder")
    parser.add_argument("--config", type=str, default="configs/training_config.yaml")
    parser.add_argument("--vq-checkpoint", type=str, required=True)
    parser.add_argument("--data-dir", type=str, required=True)
    parser.add_argument("--output-dir", type=str, default="checkpoints/dit-model")
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--num-epochs", type=int, default=100)
    parser.add_argument("--lr", type=float, default=1e-4)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--wandb-project", type=str, default="glm-image-dit")
    
    args = parser.parse_args()
    
    # Config
    config = OmegaConf.load(args.config) if Path(args.config).exists() else {}
    config = OmegaConf.to_container(config, resolve=True) if config else {}
    config["lr"] = args.lr
    
    # Wandb
    wandb.init(project=args.wandb_project, config=config)
    
    # Load VAE
    print("Loading VAE...")
    vae = AutoencoderKL.from_pretrained(
        "stabilityai/sd-vae-ft-mse",
        torch_dtype=torch.float32,
    ).cuda()
    vae.eval()
    
    # Load VQ model
    print(f"Loading VQ model from {args.vq_checkpoint}...")
    vq_checkpoint = torch.load(args.vq_checkpoint, map_location="cpu")
    vq_model = SemanticVQModel(**vq_checkpoint.get("config", {}))
    vq_model.load_state_dict(vq_checkpoint["model"])
    vq_model = vq_model.cuda()
    vq_model.eval()
    
    # Build DiT model
    print("Building DiT model...")
    dit_config = DiTConfig()
    dit_model = DiTDecoder(dit_config).cuda()
    
    # Dataset
    dataset = DiTDataset(args.data_dir, vq_model, vae)
    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=True,
    )
    
    # Trainer
    trainer = DiTTrainer(dit_model, vae, config, args.output_dir)
    
    # Train
    trainer.train(dataloader, num_epochs=args.num_epochs)
    
    print("DiT training complete!")


if __name__ == "__main__":
    main()
