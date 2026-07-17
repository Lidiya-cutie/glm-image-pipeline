"""
Vector Quantization Codebook

Реализация дискретного кодбука для семантических токенов.

Схема:
- 16384 векторов (2^14) размерности 1024
- EMA updates для стабильности
- Commitment loss для encoder
- Reset unused codes для полного использования кодбука
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange, repeat
from typing import Tuple, Optional, Dict, Any
import math


class VQCodebook(nn.Module):
    """
    Vector Quantization Codebook с EMA updates.
    
    Attributes:
        num_embeddings: Размер кодбука (default: 16384)
        embedding_dim: Размерность embedding (default: 1024)
        commitment_cost: Коэффициент commitment loss (default: 0.25)
        use_ema: Использовать EMA updates (default: True)
        ema_decay: EMA decay rate (default: 0.99)
    """
    
    def __init__(
        self,
        num_embeddings: int = 16384,
        embedding_dim: int = 1024,
        commitment_cost: float = 0.25,
        use_ema: bool = True,
        ema_decay: float = 0.99,
        ema_epsilon: float = 1e-5,
        reset_unused_codes: bool = True,
        usage_threshold: float = 1.0,
    ):
        super().__init__()
        
        self.num_embeddings = num_embeddings
        self.embedding_dim = embedding_dim
        self.commitment_cost = commitment_cost
        self.use_ema = use_ema
        self.ema_decay = ema_decay
        self.ema_epsilon = ema_epsilon
        self.reset_unused_codes = reset_unused_codes
        self.usage_threshold = usage_threshold
        
        # Codebook embeddings
        self.embedding = nn.Embedding(num_embeddings, embedding_dim)
        self._init_embeddings()
        
        if use_ema:
            # EMA cluster counts
            self.register_buffer("ema_cluster_size", torch.zeros(num_embeddings))
            # EMA sum of embeddings
            self.register_buffer("ema_embed_sum", self.embedding.weight.clone())
            
        # Usage tracking
        self.register_buffer("code_usage", torch.zeros(num_embeddings))
        self.register_buffer("usage_count", torch.tensor(0))
        
    def _init_embeddings(self):
        """Инициализация embeddings uniform в [-1/K, 1/K]."""
        limit = 1.0 / self.num_embeddings
        nn.init.uniform_(self.embedding.weight, -limit, limit)
        
    def forward(
        self, 
        z: torch.Tensor,
        return_indices: bool = True,
    ) -> Tuple[torch.Tensor, torch.Tensor, Dict[str, torch.Tensor]]:
        """
        Квантизация входных embeddings.
        
        Args:
            z: Input embeddings [B, H, W, D] или [B, N, D]
            return_indices: Возвращать ли индексы
            
        Returns:
            z_q: Quantized embeddings
            indices: Codebook indices
            losses: Dict с commitment loss и другими метриками
        """
        # Flatten spatial dimensions
        input_shape = z.shape
        flat_z = z.reshape(-1, self.embedding_dim)  # [B*H*W, D]
        
        # Compute distances: ||z - e||^2 = ||z||^2 + ||e||^2 - 2*z·e
        # [B*H*W, K]
        distances = (
            torch.sum(flat_z ** 2, dim=1, keepdim=True)
            + torch.sum(self.embedding.weight ** 2, dim=1)
            - 2 * torch.matmul(flat_z, self.embedding.weight.t())
        )
        
        # Get nearest codebook entries
        indices = torch.argmin(distances, dim=1)  # [B*H*W]
        
        # Quantize
        z_q = self.embedding(indices)  # [B*H*W, D]
        
        # Update usage tracking
        if self.training:
            self._update_usage(indices)
            
            if self.use_ema:
                self._ema_update(flat_z, indices)
                
        # Compute losses
        losses = self._compute_losses(flat_z, z_q, indices)
        
        # Straight-through estimator
        z_q = flat_z + (z_q - flat_z).detach()
        
        # Reshape back
        z_q = z_q.view(input_shape)
        indices = indices.view(input_shape[:-1])
        
        return z_q, indices, losses
    
    def _compute_losses(
        self, 
        z: torch.Tensor, 
        z_q: torch.Tensor,
        indices: torch.Tensor,
    ) -> Dict[str, torch.Tensor]:
        """Compute VQ losses."""
        losses = {}
        
        # Commitment loss: ||z - sg[e]||^2
        commitment_loss = F.mse_loss(z, z_q.detach())
        losses["commitment"] = self.commitment_cost * commitment_loss
        
        if not self.use_ema:
            # Codebook loss: ||sg[z] - e||^2
            codebook_loss = F.mse_loss(z.detach(), z_q)
            losses["codebook"] = codebook_loss
            
        # Perplexity (для мониторинга использования кодбука)
        encodings = F.one_hot(indices, self.num_embeddings).float()
        avg_probs = torch.mean(encodings, dim=0)
        perplexity = torch.exp(-torch.sum(avg_probs * torch.log(avg_probs + 1e-10)))
        losses["perplexity"] = perplexity
        
        # Codebook utilization
        unique_codes = len(torch.unique(indices))
        losses["utilization"] = torch.tensor(unique_codes / self.num_embeddings)
        
        return losses
    
    def _ema_update(self, flat_z: torch.Tensor, indices: torch.Tensor):
        """EMA update кодбука."""
        if not self.training:
            return
            
        # One-hot encodings
        encodings = F.one_hot(indices, self.num_embeddings).float()  # [B*H*W, K]
        
        # Update cluster sizes
        cluster_size = torch.sum(encodings, dim=0)  # [K]
        self.ema_cluster_size.data.mul_(self.ema_decay).add_(
            cluster_size, alpha=1 - self.ema_decay
        )
        
        # Update embedding sums
        embed_sum = torch.matmul(encodings.t(), flat_z)  # [K, D]
        self.ema_embed_sum.data.mul_(self.ema_decay).add_(
            embed_sum, alpha=1 - self.ema_decay
        )
        
        # Laplace smoothing
        n = self.ema_cluster_size.sum()
        cluster_size_smoothed = (
            (self.ema_cluster_size + self.ema_epsilon) 
            / (n + self.num_embeddings * self.ema_epsilon) * n
        )
        
        # Update embeddings
        embed_normalized = self.ema_embed_sum / cluster_size_smoothed.unsqueeze(1)
        self.embedding.weight.data.copy_(embed_normalized)
        
    def _update_usage(self, indices: torch.Tensor):
        """Track codebook usage."""
        unique_indices = torch.unique(indices)
        self.code_usage[unique_indices] += 1
        self.usage_count += 1
        
    def reset_unused(self, z_samples: Optional[torch.Tensor] = None):
        """
        Reset unused codes.
        
        Args:
            z_samples: Sample embeddings для reinitialize unused codes
        """
        if not self.reset_unused_codes:
            return
            
        avg_usage = self.code_usage / (self.usage_count + 1e-10)
        unused_mask = avg_usage < self.usage_threshold
        num_unused = unused_mask.sum().item()
        
        if num_unused > 0 and z_samples is not None:
            # Reinitialize with random samples
            sample_indices = torch.randperm(z_samples.shape[0])[:num_unused]
            new_codes = z_samples[sample_indices]
            
            unused_indices = torch.where(unused_mask)[0][:len(new_codes)]
            self.embedding.weight.data[unused_indices] = new_codes
            
            if self.use_ema:
                self.ema_cluster_size[unused_indices] = 1.0
                self.ema_embed_sum[unused_indices] = new_codes
                
        # Reset counters
        self.code_usage.zero_()
        self.usage_count.zero_()
        
    def get_codes(self, indices: torch.Tensor) -> torch.Tensor:
        """Get embeddings by indices."""
        return self.embedding(indices)
    
    def encode(self, z: torch.Tensor) -> torch.Tensor:
        """Encode to indices only."""
        _, indices, _ = self.forward(z, return_indices=True)
        return indices
    
    def decode(self, indices: torch.Tensor) -> torch.Tensor:
        """Decode from indices."""
        return self.embedding(indices)


class HierarchicalVQCodebook(nn.Module):
    """
    Иерархический VQ кодбук с несколькими уровнями детализации.
    
    Coarse level: глобальный layout
    Fine level: локальные детали
    """
    
    def __init__(
        self,
        num_levels: int = 2,
        level_sizes: Tuple[int, ...] = (4096, 16384),
        embedding_dim: int = 1024,
        commitment_cost: float = 0.25,
    ):
        super().__init__()
        
        self.num_levels = num_levels
        self.codebooks = nn.ModuleList([
            VQCodebook(
                num_embeddings=size,
                embedding_dim=embedding_dim,
                commitment_cost=commitment_cost,
            )
            for size in level_sizes
        ])
        
        # Residual projections между уровнями
        self.residual_projections = nn.ModuleList([
            nn.Linear(embedding_dim, embedding_dim)
            for _ in range(num_levels - 1)
        ])
        
    def forward(
        self, 
        z: torch.Tensor
    ) -> Tuple[torch.Tensor, list, Dict[str, torch.Tensor]]:
        """
        Иерархическая квантизация.
        
        Returns:
            z_q: Final quantized embedding
            all_indices: List of indices per level
            losses: Combined losses
        """
        all_indices = []
        all_losses = {}
        residual = z
        z_q_total = torch.zeros_like(z)
        
        for level, codebook in enumerate(self.codebooks):
            z_q, indices, losses = codebook(residual)
            
            all_indices.append(indices)
            for k, v in losses.items():
                all_losses[f"level_{level}_{k}"] = v
                
            z_q_total = z_q_total + z_q
            
            # Compute residual for next level
            if level < self.num_levels - 1:
                residual = residual - z_q
                residual = self.residual_projections[level](residual)
                
        return z_q_total, all_indices, all_losses
