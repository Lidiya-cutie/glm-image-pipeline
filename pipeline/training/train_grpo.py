#!/usr/bin/env python3
"""
Stage 4: GRPO Fine-tuning (Reinforcement Learning)

Decoupled GRPO для улучшения качества:
- AR Model: rewards за семантику, layout, alignment
- DiT Model: rewards за качество текста (OCR), детали, эстетику

Запуск AR GRPO:
    python -m pipeline.training.train_grpo \
        --mode ar \
        --ar-checkpoint checkpoints/ar-model/best.pt \
        --dit-checkpoint checkpoints/dit-model/best.pt \
        --vq-checkpoint checkpoints/vq-encoder/best.pt \
        --output-dir checkpoints/ar-model-grpo

Запуск DiT Flow-GRPO:
    python -m pipeline.training.train_grpo \
        --mode dit \
        --ar-checkpoint checkpoints/ar-model-grpo/best.pt \
        --dit-checkpoint checkpoints/dit-model/best.pt \
        --vq-checkpoint checkpoints/vq-encoder/best.pt \
        --output-dir checkpoints/dit-model-grpo
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
from tqdm import tqdm
import wandb
from omegaconf import OmegaConf
from typing import Optional, Dict, Any, List, Tuple
import json
from PIL import Image
import numpy as np

from transformers import AutoTokenizer, CLIPModel, CLIPProcessor
from diffusers import AutoencoderKL

from models.ar_model import GLMImageARModel, GLMImageARConfig
from models.dit_decoder import DiTDecoder, DiTConfig
from models.vq_encoder import SemanticVQModel
from models.glyph_encoder import GlyphEncoder, TextAccuracyMetrics


class RewardModel:
    """
    Reward model combining multiple metrics.
    
    For AR:
        - CLIP score (text-image alignment)
        - Layout quality (learned classifier)
        
    For DiT:
        - Text accuracy (OCR)
        - Aesthetic score
        - Detail quality (LPIPS)
    """
    
    def __init__(self, device: str = "cuda"):
        self.device = device
        
        # CLIP for text-image alignment
        print("Loading CLIP...")
        self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-large-patch14").to(device)
        self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-large-patch14")
        self.clip_model.eval()
        
        # OCR for text accuracy
        print("Loading Glyph Encoder...")
        self.glyph_encoder = GlyphEncoder(device=device)
        self.text_metrics = TextAccuracyMetrics()
        
        # Aesthetic predictor (optional)
        self.aesthetic_model = None
        
    @torch.no_grad()
    def compute_clip_score(
        self,
        images: List[Image.Image],
        texts: List[str],
    ) -> torch.Tensor:
        """Compute CLIP similarity scores."""
        inputs = self.clip_processor(
            text=texts,
            images=images,
            return_tensors="pt",
            padding=True,
        ).to(self.device)
        
        outputs = self.clip_model(**inputs)
        
        # Normalize and compute similarity
        image_embeds = outputs.image_embeds / outputs.image_embeds.norm(dim=-1, keepdim=True)
        text_embeds = outputs.text_embeds / outputs.text_embeds.norm(dim=-1, keepdim=True)
        
        # Diagonal similarity (each image with its text)
        similarity = (image_embeds * text_embeds).sum(dim=-1)
        
        return similarity
    
    @torch.no_grad()
    def compute_text_accuracy(
        self,
        images: List[Image.Image],
        target_texts: List[str],
    ) -> Dict[str, torch.Tensor]:
        """Compute text rendering accuracy via OCR."""
        word_accs = []
        neds = []
        
        for img, target in zip(images, target_texts):
            result = self.glyph_encoder.recognize(img)
            recognized = result["text"]
            
            metrics = self.text_metrics.compute_all(target, recognized)
            word_accs.append(metrics["word_accuracy"])
            neds.append(metrics["ned_reward"])
            
        return {
            "word_accuracy": torch.tensor(word_accs),
            "ned": torch.tensor(neds),
        }
    
    def compute_ar_rewards(
        self,
        images: List[Image.Image],
        prompts: List[str],
    ) -> torch.Tensor:
        """
        Compute rewards for AR model.
        
        Focus on semantic alignment and layout.
        """
        # CLIP score
        clip_scores = self.compute_clip_score(images, prompts)
        
        # Combine rewards
        rewards = clip_scores  # Can add layout score here
        
        return rewards
    
    def compute_dit_rewards(
        self,
        images: List[Image.Image],
        prompts: List[str],
        target_texts: List[str],
    ) -> torch.Tensor:
        """
        Compute rewards for DiT model.
        
        Focus on text accuracy and visual quality.
        """
        # Text accuracy
        text_metrics = self.compute_text_accuracy(images, target_texts)
        
        # CLIP score (for general quality)
        clip_scores = self.compute_clip_score(images, prompts)
        
        # Combine rewards
        rewards = (
            0.5 * text_metrics["word_accuracy"].to(self.device) +
            0.3 * text_metrics["ned"].to(self.device) +
            0.2 * clip_scores
        )
        
        return rewards


class GRPOTrainer:
    """
    Group Relative Policy Optimization trainer.
    
    GRPO algorithm:
        1. Generate K samples for each prompt
        2. Compute rewards for all samples
        3. Compute relative advantages within group
        4. Update policy with clipped objective
    """
    
    def __init__(
        self,
        model: nn.Module,
        ref_model: nn.Module,  # Reference model for KL
        reward_model: RewardModel,
        config: Dict[str, Any],
        output_dir: str,
        device: str = "cuda",
    ):
        self.model = model
        self.ref_model = ref_model
        self.reward_model = reward_model
        self.config = config
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.device = device
        
        # GRPO params
        self.num_samples = config.get("num_samples", 4)  # K samples per prompt
        self.beta = config.get("beta", 0.1)  # KL penalty
        self.clip_ratio = config.get("clip_ratio", 0.2)
        
        # Optimizer
        self.optimizer = torch.optim.AdamW(
            model.parameters(),
            lr=config.get("lr", 1e-6),
            weight_decay=0.01,
        )
        
        self.global_step = 0
        
    def compute_log_probs(
        self,
        model: nn.Module,
        input_ids: torch.Tensor,
        target_ids: torch.Tensor,
    ) -> torch.Tensor:
        """Compute log probabilities of target tokens."""
        with torch.no_grad() if model == self.ref_model else torch.enable_grad():
            outputs = model(input_ids=input_ids)
            logits = outputs.logits[:, :-1]  # Shift
            
            log_probs = F.log_softmax(logits, dim=-1)
            target_log_probs = log_probs.gather(-1, target_ids[:, 1:].unsqueeze(-1)).squeeze(-1)
            
            # Sum over sequence
            return target_log_probs.sum(dim=-1)
    
    def grpo_step(
        self,
        prompts: List[str],
        target_texts: List[str],  # Text to render
    ) -> Dict[str, float]:
        """
        Single GRPO training step.
        
        1. Generate K samples per prompt
        2. Compute rewards
        3. Compute advantages (group-relative)
        4. Policy gradient update
        """
        self.model.train()
        batch_size = len(prompts)
        
        # Generate K samples per prompt
        all_samples = []
        all_log_probs = []
        all_ref_log_probs = []
        
        for prompt in prompts:
            samples = []
            for _ in range(self.num_samples):
                # Generate sample
                with torch.no_grad():
                    sample = self._generate_sample(prompt)
                samples.append(sample)
            all_samples.append(samples)
            
        # Compute rewards (need to decode samples to images)
        all_rewards = []
        for i, (prompt, target, samples) in enumerate(zip(prompts, target_texts, all_samples)):
            rewards = []
            for sample in samples:
                # Decode to image (this is simplified - actual implementation needs full pipeline)
                # For now, use placeholder reward
                reward = torch.rand(1).item()  # Placeholder
                rewards.append(reward)
            all_rewards.append(torch.tensor(rewards))
            
        # Stack rewards and compute group-relative advantages
        rewards = torch.stack(all_rewards)  # [batch, K]
        
        # Advantages: normalize within each group
        advantages = rewards - rewards.mean(dim=1, keepdim=True)
        advantages = advantages / (advantages.std(dim=1, keepdim=True) + 1e-8)
        
        # Compute policy gradient loss
        total_loss = 0
        for i in range(batch_size):
            for j in range(self.num_samples):
                # This is simplified - actual implementation needs proper log prob computation
                advantage = advantages[i, j]
                
                # Policy gradient: -advantage * log_prob
                # With clipping like PPO
                loss = -advantage  # Simplified
                total_loss += loss
                
        total_loss = total_loss / (batch_size * self.num_samples)
        
        # Backward
        self.optimizer.zero_grad()
        if isinstance(total_loss, torch.Tensor):
            total_loss.backward()
            self.optimizer.step()
            
        self.global_step += 1
        
        return {
            "loss": total_loss.item() if isinstance(total_loss, torch.Tensor) else total_loss,
            "mean_reward": rewards.mean().item(),
            "reward_std": rewards.std().item(),
        }
    
    def _generate_sample(self, prompt: str) -> torch.Tensor:
        """Generate single sample (implemented in subclass)."""
        raise NotImplementedError
        
    def train(
        self,
        prompts: List[str],
        target_texts: List[str],
        num_iterations: int = 10000,
        batch_size: int = 8,
    ):
        """Training loop."""
        print(f"Starting GRPO training for {num_iterations} iterations")
        
        for iteration in range(num_iterations):
            # Sample batch
            indices = np.random.choice(len(prompts), batch_size, replace=False)
            batch_prompts = [prompts[i] for i in indices]
            batch_targets = [target_texts[i] for i in indices]
            
            # GRPO step
            metrics = self.grpo_step(batch_prompts, batch_targets)
            
            if iteration % 10 == 0:
                print(f"Iter {iteration}: {metrics}")
                wandb.log(metrics, step=self.global_step)
                
            # Save checkpoint
            if (iteration + 1) % 1000 == 0:
                self.save_checkpoint(iteration)
                
    def save_checkpoint(self, iteration: int):
        """Save checkpoint."""
        checkpoint = {
            "iteration": iteration,
            "model": self.model.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "config": self.config,
        }
        
        path = self.output_dir / f"checkpoint_iter_{iteration}.pt"
        torch.save(checkpoint, path)
        print(f"Saved checkpoint to {path}")


class ARGRPOTrainer(GRPOTrainer):
    """GRPO trainer specifically for AR model."""
    
    def __init__(
        self,
        ar_model: GLMImageARModel,
        tokenizer,
        vq_model: SemanticVQModel,
        dit_model: DiTDecoder,
        vae: AutoencoderKL,
        **kwargs,
    ):
        # Create reference model (frozen copy)
        ref_model = GLMImageARModel(ar_model.config)
        ref_model.load_state_dict(ar_model.state_dict())
        ref_model.eval()
        for p in ref_model.parameters():
            p.requires_grad = False
            
        reward_model = RewardModel(kwargs.get("device", "cuda"))
        
        super().__init__(ar_model, ref_model, reward_model, **kwargs)
        
        self.tokenizer = tokenizer
        self.vq_model = vq_model
        self.dit_model = dit_model
        self.vae = vae
        
    def _generate_sample(self, prompt: str) -> torch.Tensor:
        """Generate VQ tokens for prompt."""
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        
        output = self.model.generate_vq_tokens(
            input_ids=inputs["input_ids"],
            max_new_tokens=4096,
            temperature=0.9,
            top_p=0.95,
        )
        
        return output


class DiTFlowGRPOTrainer(GRPOTrainer):
    """
    Flow-GRPO trainer for DiT model.
    
    Adapts GRPO for diffusion models by:
    - Computing rewards on generated images
    - Backprop through truncated diffusion trajectory
    """
    
    def __init__(
        self,
        dit_model: DiTDecoder,
        vq_model: SemanticVQModel,
        ar_model: GLMImageARModel,
        vae: AutoencoderKL,
        **kwargs,
    ):
        ref_model = DiTDecoder(dit_model.config)
        ref_model.load_state_dict(dit_model.state_dict())
        ref_model.eval()
        for p in ref_model.parameters():
            p.requires_grad = False
            
        reward_model = RewardModel(kwargs.get("device", "cuda"))
        
        super().__init__(dit_model, ref_model, reward_model, **kwargs)
        
        self.vq_model = vq_model
        self.ar_model = ar_model
        self.vae = vae
        
    def _generate_sample(self, prompt: str) -> torch.Tensor:
        """Generate image for prompt."""
        # This would use the full pipeline
        # Simplified for now
        return torch.randn(3, 1024, 1024)


def load_prompts(path: str) -> Tuple[List[str], List[str]]:
    """Load prompts and target texts from JSON."""
    with open(path) as f:
        data = json.load(f)
        
    prompts = [item["prompt"] for item in data]
    targets = [item.get("target_text", "") for item in data]
    
    return prompts, targets


def main():
    parser = argparse.ArgumentParser(description="GRPO Training")
    parser.add_argument("--mode", type=str, required=True, choices=["ar", "dit"])
    parser.add_argument("--ar-checkpoint", type=str, required=True)
    parser.add_argument("--dit-checkpoint", type=str, required=True)
    parser.add_argument("--vq-checkpoint", type=str, required=True)
    parser.add_argument("--prompts", type=str, required=True,
                        help="JSON file with prompts")
    parser.add_argument("--output-dir", type=str, required=True)
    parser.add_argument("--num-iterations", type=int, default=10000)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-6)
    parser.add_argument("--wandb-project", type=str, default="glm-image-grpo")
    
    args = parser.parse_args()
    
    # Wandb
    wandb.init(project=args.wandb_project, config=vars(args))
    
    # Load models
    print("Loading models...")
    
    # VQ
    vq_ckpt = torch.load(args.vq_checkpoint, map_location="cpu")
    vq_model = SemanticVQModel(**vq_ckpt.get("config", {}))
    vq_model.load_state_dict(vq_ckpt["model"])
    vq_model = vq_model.cuda().eval()
    
    # VAE
    vae = AutoencoderKL.from_pretrained("stabilityai/sd-vae-ft-mse").cuda()
    
    # AR
    ar_ckpt = torch.load(args.ar_checkpoint, map_location="cpu")
    ar_config = GLMImageARConfig(**ar_ckpt.get("config", {}))
    ar_model = GLMImageARModel(ar_config)
    ar_model.load_state_dict(ar_ckpt["model"])
    ar_model = ar_model.cuda()
    
    # DiT
    dit_ckpt = torch.load(args.dit_checkpoint, map_location="cpu")
    dit_config = DiTConfig(**dit_ckpt.get("config", {}))
    dit_model = DiTDecoder(dit_config)
    dit_model.load_state_dict(dit_ckpt["model"])
    dit_model = dit_model.cuda()
    
    # Tokenizer
    try:
        tokenizer = AutoTokenizer.from_pretrained("THUDM/glm-4-9b-chat", trust_remote_code=True)
    except:
        tokenizer = AutoTokenizer.from_pretrained("gpt2")
        tokenizer.pad_token = tokenizer.eos_token
        
    # Load prompts
    prompts, targets = load_prompts(args.prompts)
    print(f"Loaded {len(prompts)} prompts")
    
    # Create trainer
    config = {"lr": args.lr, "num_samples": 4, "beta": 0.1}
    
    if args.mode == "ar":
        trainer = ARGRPOTrainer(
            ar_model=ar_model,
            tokenizer=tokenizer,
            vq_model=vq_model,
            dit_model=dit_model,
            vae=vae,
            config=config,
            output_dir=args.output_dir,
        )
    else:
        trainer = DiTFlowGRPOTrainer(
            dit_model=dit_model,
            vq_model=vq_model,
            ar_model=ar_model,
            vae=vae,
            config=config,
            output_dir=args.output_dir,
        )
        
    # Train
    trainer.train(prompts, targets, num_iterations=args.num_iterations, batch_size=args.batch_size)
    
    print("GRPO training complete!")


if __name__ == "__main__":
    main()
