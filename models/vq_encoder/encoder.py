"""
Semantic VQ Encoder

Преобразует изображение в последовательность семантических VQ токенов.
Используется ViT backbone для извлечения патч-level features.

Pipeline:
  Image [B, 3, H, W] 
    → ViT Backbone [B, N_patches, D_vit]
    → Projection [B, N_patches, D_vq]
    → VQ Codebook → [B, N_patches] token IDs
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange, repeat
from typing import Tuple, Optional, Dict, Any, List
import math

try:
    import timm
except ImportError as e:
    timm = None
    _TIMM_IMPORT_ERROR = e
else:
    _TIMM_IMPORT_ERROR = None


class PatchEmbedding(nn.Module):
    """Conv-based patch embedding."""
    
    def __init__(
        self,
        img_size: int = 512,
        patch_size: int = 16,
        in_channels: int = 3,
        embed_dim: int = 1024,
    ):
        super().__init__()
        self.img_size = img_size
        self.patch_size = patch_size
        self.num_patches = (img_size // patch_size) ** 2
        self.grid_size = img_size // patch_size
        
        self.proj = nn.Conv2d(
            in_channels, embed_dim, 
            kernel_size=patch_size, 
            stride=patch_size
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [B, C, H, W]
        Returns:
            [B, H//P * W//P, D]
        """
        x = self.proj(x)  # [B, D, H/P, W/P]
        x = rearrange(x, 'b d h w -> b (h w) d')
        return x


class SemanticVQEncoder(nn.Module):
    """
    Semantic VQ Encoder.
    
    Архитектура:
    1. ViT backbone (pretrained) для извлечения семантических features
    2. Projection head для преобразования в VQ embedding space
    3. Spatial position encoding для сохранения layout информации
    
    Args:
        backbone: ViT backbone name (default: "vit_large_patch16_384")
        embedding_dim: VQ embedding dimension (default: 1024)
        patch_size: Patch size (default: 16)
        pretrained: Use pretrained backbone (default: True)
    """
    
    def __init__(
        self,
        backbone: str = "vit_large_patch16_384",
        embedding_dim: int = 1024,
        patch_size: int = 16,
        pretrained: bool = True,
        freeze_backbone: bool = False,
        projection_hidden_dims: List[int] = [2048, 1024],
        dropout: float = 0.1,
    ):
        super().__init__()
        
        if timm is None:
            raise ImportError(
                "timm is required for SemanticVQEncoder. Install: pip install timm"
            ) from _TIMM_IMPORT_ERROR

        self.embedding_dim = embedding_dim
        self.patch_size = patch_size
        
        # ViT Backbone
        self.backbone = timm.create_model(
            backbone,
            pretrained=pretrained,
            num_classes=0,  # Remove classifier
            global_pool="",  # Keep spatial tokens
        )
        
        # Get backbone output dim
        self.backbone_dim = self.backbone.embed_dim
        
        if freeze_backbone:
            for param in self.backbone.parameters():
                param.requires_grad = False
                
        # Projection head: backbone_dim → embedding_dim
        projection_layers = []
        in_dim = self.backbone_dim
        
        for hidden_dim in projection_hidden_dims:
            projection_layers.extend([
                nn.Linear(in_dim, hidden_dim),
                nn.GELU(),
                nn.Dropout(dropout),
            ])
            in_dim = hidden_dim
            
        projection_layers.append(nn.Linear(in_dim, embedding_dim))
        self.projection = nn.Sequential(*projection_layers)
        
        # Layer norm
        self.pre_norm = nn.LayerNorm(self.backbone_dim)
        self.post_norm = nn.LayerNorm(embedding_dim)
        
        # 2D Positional encoding для сохранения spatial layout
        self.pos_embed = None  # Initialized dynamically
        
    def _get_pos_embed(self, h: int, w: int, device: torch.device) -> torch.Tensor:
        """Get 2D sinusoidal positional embeddings."""
        # Create 2D position grid
        y_pos = torch.arange(h, device=device).float()
        x_pos = torch.arange(w, device=device).float()
        y_grid, x_grid = torch.meshgrid(y_pos, x_pos, indexing='ij')
        
        # Sinusoidal encoding
        dim = self.embedding_dim
        omega = torch.arange(dim // 4, device=device).float()
        omega = 1.0 / (10000 ** (omega / (dim // 4)))
        
        # [H, W, D/4]
        y_embed = y_grid.unsqueeze(-1) * omega
        x_embed = x_grid.unsqueeze(-1) * omega
        
        # Concatenate sin/cos for both x and y
        pos_embed = torch.cat([
            torch.sin(y_embed), torch.cos(y_embed),
            torch.sin(x_embed), torch.cos(x_embed),
        ], dim=-1)  # [H, W, D]
        
        return pos_embed.reshape(h * w, -1)  # [H*W, D]
        
    def forward(
        self, 
        images: torch.Tensor,
        return_features: bool = False,
    ) -> Tuple[torch.Tensor, Dict[str, Any]]:
        """
        Encode images to semantic embeddings.
        
        Args:
            images: [B, 3, H, W] normalized images
            return_features: Return intermediate features
            
        Returns:
            z: [B, H//P, W//P, D] semantic embeddings
            info: Dict with grid size, features etc.
        """
        B, C, H, W = images.shape
        
        # Compute grid size
        grid_h = H // self.patch_size
        grid_w = W // self.patch_size
        
        # ViT forward
        # timm ViT returns [B, N+1, D] with cls token, or [B, N, D] without
        features = self.backbone.forward_features(images)
        
        # Remove CLS token if present
        if features.shape[1] == grid_h * grid_w + 1:
            features = features[:, 1:]  # [B, H*W, D_backbone]
            
        # Pre-norm
        features = self.pre_norm(features)
        
        # Project to VQ embedding space
        z = self.projection(features)  # [B, H*W, D_vq]
        
        # Add 2D positional encoding
        pos_embed = self._get_pos_embed(grid_h, grid_w, z.device)
        z = z + pos_embed.unsqueeze(0)
        
        # Post-norm
        z = self.post_norm(z)
        
        # Reshape to spatial
        z = rearrange(z, 'b (h w) d -> b h w d', h=grid_h, w=grid_w)
        
        info = {
            "grid_size": (grid_h, grid_w),
            "num_tokens": grid_h * grid_w,
        }
        
        if return_features:
            info["backbone_features"] = features
            
        return z, info
    
    def encode_to_indices(
        self, 
        images: torch.Tensor, 
        codebook: nn.Module
    ) -> Tuple[torch.Tensor, Dict[str, Any]]:
        """
        Full encoding: image → VQ indices.
        
        Args:
            images: [B, 3, H, W]
            codebook: VQCodebook instance
            
        Returns:
            indices: [B, H//P, W//P] token IDs
            info: Dict with losses and metrics
        """
        # Get embeddings
        z, info = self.forward(images)
        
        # Quantize
        z_q, indices, vq_losses = codebook(z)
        
        info.update(vq_losses)
        info["z_q"] = z_q
        
        return indices, info


class ConvSemanticEncoder(nn.Module):
    """
    CNN-based semantic encoder (альтернатива ViT).
    
    Использует иерархический CNN для multi-scale features.
    """
    
    def __init__(
        self,
        in_channels: int = 3,
        embedding_dim: int = 1024,
        base_channels: int = 64,
        num_downsample: int = 4,  # 16x downsampling
    ):
        super().__init__()
        
        self.embedding_dim = embedding_dim
        self.downsample_factor = 2 ** num_downsample
        
        # Encoder blocks
        channels = [base_channels * (2 ** i) for i in range(num_downsample + 1)]
        
        self.stem = nn.Sequential(
            nn.Conv2d(in_channels, channels[0], 7, stride=2, padding=3),
            nn.GroupNorm(8, channels[0]),
            nn.GELU(),
        )
        
        self.down_blocks = nn.ModuleList()
        for i in range(num_downsample):
            self.down_blocks.append(
                self._make_down_block(channels[i], channels[i + 1])
            )
            
        # Final projection
        self.proj = nn.Sequential(
            nn.Conv2d(channels[-1], embedding_dim, 1),
            nn.GroupNorm(32, embedding_dim),
        )
        
    def _make_down_block(self, in_ch: int, out_ch: int) -> nn.Module:
        return nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, stride=2, padding=1),
            nn.GroupNorm(min(32, out_ch), out_ch),
            nn.GELU(),
            nn.Conv2d(out_ch, out_ch, 3, padding=1),
            nn.GroupNorm(min(32, out_ch), out_ch),
            nn.GELU(),
        )
        
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, Any]]:
        """
        Args:
            x: [B, 3, H, W]
        Returns:
            z: [B, H//16, W//16, D]
        """
        B, C, H, W = x.shape
        
        x = self.stem(x)  # [B, C0, H/2, W/2]
        
        for block in self.down_blocks:
            x = block(x)
            
        x = self.proj(x)  # [B, D, H/16, W/16]
        
        # Rearrange to [B, H, W, D]
        x = rearrange(x, 'b d h w -> b h w d')
        
        grid_h, grid_w = H // self.downsample_factor, W // self.downsample_factor
        
        return x, {
            "grid_size": (grid_h, grid_w),
            "num_tokens": grid_h * grid_w,
        }
