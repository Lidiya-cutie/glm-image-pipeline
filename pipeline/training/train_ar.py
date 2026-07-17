#!/usr/bin/env python3
"""
Stage 2: AR Model Training

Обучает авторегрессионную модель генерировать VQ токены по текстовому промпту.

Запуск:
    python -m pipeline.training.train_ar \
        --config configs/training_config.yaml \
        --base-model THUDM/glm-4-9b-chat \
        --data-dir data/vq-tokens \
        --output-dir checkpoints/ar-model \
        --deepspeed configs/deepspeed_zero3.json

Формат данных:
    data/vq-tokens/
    ├── 00000.pt  # {"text": "...", "vq_tokens": tensor([...])}
    ├── 00001.pt
    └── ...

Что происходит:
    1. Загружаем GLM-4 как базовую модель
    2. Расширяем vocabulary на VQ токены (+16384)
    3. Обучаем предсказывать VQ токены авторегрессионно
    4. Loss: cross-entropy с повышенным весом для layout токенов
"""

import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm
import wandb
from omegaconf import OmegaConf
from typing import Optional, Dict, Any, List
import json

from transformers import AutoTokenizer, get_cosine_schedule_with_warmup
from models.ar_model import GLMImageARModel, GLMImageARConfig
from models.ar_model.generation import create_layout_weight_mask


class VQTokenDataset(Dataset):
    """
    Dataset с парами (text, vq_tokens).
    
    Формат файла:
        {
            "text": "A poster with text 'Hello World'",
            "vq_tokens": [1234, 5678, ...],  # 4096 токенов для 1024x1024
            "metadata": {"width": 1024, "height": 1024}
        }
    """
    
    def __init__(
        self,
        data_dir: str,
        tokenizer,
        max_text_length: int = 512,
        max_vq_tokens: int = 4096,
        vq_offset: int = 135168,
    ):
        self.data_dir = Path(data_dir)
        self.tokenizer = tokenizer
        self.max_text_length = max_text_length
        self.max_vq_tokens = max_vq_tokens
        self.vq_offset = vq_offset
        
        # Special tokens
        self.image_start_id = 135000
        self.image_end_id = 135001
        
        # Collect all data files
        self.data_files = sorted(self.data_dir.glob("*.pt"))
        if not self.data_files:
            self.data_files = sorted(self.data_dir.glob("*.json"))
            
        print(f"Found {len(self.data_files)} training samples")
        
    def __len__(self):
        return len(self.data_files)
    
    def __getitem__(self, idx):
        filepath = self.data_files[idx]
        
        # Load data
        if filepath.suffix == ".pt":
            data = torch.load(filepath)
        else:
            with open(filepath) as f:
                data = json.load(f)
                
        text = data["text"]
        vq_tokens = data["vq_tokens"]
        
        if isinstance(vq_tokens, list):
            vq_tokens = torch.tensor(vq_tokens)
            
        # Tokenize text
        text_encoding = self.tokenizer(
            text,
            max_length=self.max_text_length,
            truncation=True,
            return_tensors="pt",
        )
        text_ids = text_encoding["input_ids"].squeeze(0)
        
        # Build sequence: [text] [IMAGE_START] [vq_tokens] [IMAGE_END]
        image_start = torch.tensor([self.image_start_id])
        image_end = torch.tensor([self.image_end_id])
        vq_ids = vq_tokens[:self.max_vq_tokens] + self.vq_offset
        
        input_ids = torch.cat([text_ids, image_start, vq_ids, image_end])
        
        # Labels (same as input for AR)
        labels = input_ids.clone()
        # Mask text tokens in labels (only predict VQ)
        labels[:len(text_ids) + 1] = -100  # text + IMAGE_START
        
        # Create attention mask
        attention_mask = torch.ones_like(input_ids)
        
        # Create weight mask for layout tokens
        weight_mask = torch.ones_like(input_ids, dtype=torch.float)
        # Higher weight for first 256 VQ tokens (layout)
        vq_start = len(text_ids) + 1  # After text + IMAGE_START
        layout_end = min(vq_start + 256, len(input_ids))
        weight_mask[vq_start:layout_end] = 2.0  # 2x weight for layout
        
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": labels,
            "weight_mask": weight_mask,
        }


def collate_fn(batch):
    """Pad sequences to same length."""
    max_len = max(item["input_ids"].size(0) for item in batch)
    
    input_ids = []
    attention_mask = []
    labels = []
    weight_mask = []
    
    for item in batch:
        pad_len = max_len - item["input_ids"].size(0)
        
        input_ids.append(F.pad(item["input_ids"], (0, pad_len), value=0))
        attention_mask.append(F.pad(item["attention_mask"], (0, pad_len), value=0))
        labels.append(F.pad(item["labels"], (0, pad_len), value=-100))
        weight_mask.append(F.pad(item["weight_mask"], (0, pad_len), value=0))
        
    return {
        "input_ids": torch.stack(input_ids),
        "attention_mask": torch.stack(attention_mask),
        "labels": torch.stack(labels),
        "weight_mask": torch.stack(weight_mask),
    }


class ARTrainer:
    """
    AR Model Trainer.
    
    Supports:
        - DeepSpeed ZeRO-3 for large models
        - Gradient checkpointing
        - Layout-weighted loss
    """
    
    def __init__(
        self,
        model: GLMImageARModel,
        tokenizer,
        config: Dict[str, Any],
        output_dir: str,
        device: str = "cuda",
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.device = device
        
        # Optimizer
        self.optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.get("lr", 5e-5),
            betas=(0.9, 0.95),
            weight_decay=config.get("weight_decay", 0.1),
        )
        
        self.global_step = 0
        self.scaler = torch.cuda.amp.GradScaler()
        
    def train_step(self, batch: Dict[str, torch.Tensor]) -> Dict[str, float]:
        """Single training step."""
        self.model.train()
        
        input_ids = batch["input_ids"].to(self.device)
        attention_mask = batch["attention_mask"].to(self.device)
        labels = batch["labels"].to(self.device)
        weight_mask = batch["weight_mask"].to(self.device)
        
        with torch.cuda.amp.autocast():
            outputs = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                labels=labels,
                vq_weight_mask=weight_mask,
            )
            loss = outputs.loss
            
        # Backward
        self.optimizer.zero_grad()
        self.scaler.scale(loss).backward()
        self.scaler.unscale_(self.optimizer)
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.scaler.step(self.optimizer)
        self.scaler.update()
        
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
    def generate_sample(self, prompt: str) -> List[int]:
        """Generate sample VQ tokens for validation."""
        self.model.eval()
        
        # Tokenize
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        
        # Generate
        output = self.model.generate_vq_tokens(
            input_ids=inputs["input_ids"],
            max_new_tokens=4096,
            temperature=0.9,
            top_p=0.95,
        )
        
        return output[0].tolist()
    
    def save_checkpoint(self, epoch: int, metrics: Dict[str, float]):
        """Save checkpoint."""
        checkpoint = {
            "epoch": epoch,
            "model": self.model.state_dict(),
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
        print(f"Starting AR training for {num_epochs} epochs")
        
        for epoch in range(num_epochs):
            metrics = self.train_epoch(dataloader, epoch)
            print(f"Epoch {epoch}: {metrics}")
            
            # Save checkpoint every 5 epochs
            if (epoch + 1) % 5 == 0:
                self.save_checkpoint(epoch, metrics)
                
            # Generate samples for validation
            if (epoch + 1) % 10 == 0:
                sample = self.generate_sample("A poster with bold text")
                print(f"Generated {len(sample)} VQ tokens")


def main():
    parser = argparse.ArgumentParser(description="Train AR Model")
    parser.add_argument("--config", type=str, default="configs/training_config.yaml")
    parser.add_argument("--base-model", type=str, default="THUDM/glm-4-9b-chat",
                        help="Base model to initialize from")
    parser.add_argument("--data-dir", type=str, required=True)
    parser.add_argument("--output-dir", type=str, default="checkpoints/ar-model")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--num-epochs", type=int, default=50)
    parser.add_argument("--lr", type=float, default=5e-5)
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--deepspeed", type=str, default=None)
    parser.add_argument("--wandb-project", type=str, default="glm-image-ar")
    
    args = parser.parse_args()
    
    # Load config
    config = OmegaConf.load(args.config)
    config = OmegaConf.to_container(config, resolve=True)
    config["lr"] = args.lr
    
    # Init wandb
    wandb.init(project=args.wandb_project, config=config)
    
    # Load tokenizer
    print(f"Loading tokenizer from {args.base_model}...")
    try:
        tokenizer = AutoTokenizer.from_pretrained(
            args.base_model,
            trust_remote_code=True,
        )
    except:
        print("Using GPT-2 tokenizer as fallback")
        tokenizer = AutoTokenizer.from_pretrained("gpt2")
        tokenizer.pad_token = tokenizer.eos_token
        
    # Build model
    print(f"Building AR model from {args.base_model}...")
    model_config = GLMImageARConfig()
    
    # Try to load from base model
    try:
        model = GLMImageARModel.from_glm4(args.base_model, model_config)
        print("Initialized from GLM-4")
    except:
        print("Creating model from scratch")
        model = GLMImageARModel(model_config)
        
    model = model.cuda()
    
    # Dataset
    dataset = VQTokenDataset(args.data_dir, tokenizer)
    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        collate_fn=collate_fn,
        pin_memory=True,
    )
    
    # Trainer
    trainer = ARTrainer(model, tokenizer, config, args.output_dir)
    
    # Train
    trainer.train(dataloader, num_epochs=args.num_epochs)
    
    print("AR training complete!")


if __name__ == "__main__":
    # Import F for collate_fn
    import torch.nn.functional as F
    main()
