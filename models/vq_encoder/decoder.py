"""
Semantic VQ Decoder

Декодер для реконструкции изображений из VQ токенов.
Используется при обучении VQ encoder (не при инференсе - там DiT).

Pipeline:
  VQ Tokens [B, H, W] 
    → Codebook Lookup [B, H, W, D]
    → Upsampling Decoder [B, 3, H*16, W*16]
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange, repeat
from typing import Tuple, Optional, Dict, Any, List
import math


class ResBlock(nn.Module):
    """Residual block with GroupNorm."""
    
    def __init__(
        self, 
        channels: int, 
        out_channels: Optional[int] = None,
        dropout: float = 0.0,
    ):
        super().__init__()
        out_channels = out_channels or channels
        
        self.conv1 = nn.Conv2d(channels, out_channels, 3, padding=1)
        self.conv2 = nn.Conv2d(out_channels, out_channels, 3, padding=1)
        self.norm1 = nn.GroupNorm(32, channels)
        self.norm2 = nn.GroupNorm(32, out_channels)
        self.dropout = nn.Dropout(dropout)
        self.act = nn.GELU()
        
        if channels != out_channels:
            self.skip = nn.Conv2d(channels, out_channels, 1)
        else:
            self.skip = nn.Identity()
            
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        h = self.norm1(x)
        h = self.act(h)
        h = self.conv1(h)
        
        h = self.norm2(h)
        h = self.act(h)
        h = self.dropout(h)
        h = self.conv2(h)
        
        return h + self.skip(x)


class Upsample(nn.Module):
    """Learnable upsampling."""
    
    def __init__(self, channels: int, use_conv: bool = True):
        super().__init__()
        self.use_conv = use_conv
        if use_conv:
            self.conv = nn.Conv2d(channels, channels, 3, padding=1)
            
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.interpolate(x, scale_factor=2, mode='nearest')
        if self.use_conv:
            x = self.conv(x)
        return x


class SemanticVQDecoder(nn.Module):
    """
    CNN-based decoder для реконструкции из VQ embeddings.
    
    Архитектура:
    1. Input projection: [B, H, W, D] → [B, C, H, W]
    2. Hierarchical upsampling с residual blocks
    3. Final conv: [B, C, H*16, W*16] → [B, 3, H*16, W*16]
    
    Args:
        embedding_dim: VQ embedding dimension (default: 1024)
        out_channels: Output image channels (default: 3)
        base_channels: Base channel count (default: 256)
        num_upsample: Number of 2x upsampling (default: 4 for 16x total)
        num_res_blocks: Residual blocks per resolution (default: 2)
    """
    
    def __init__(
        self,
        embedding_dim: int = 1024,
        out_channels: int = 3,
        base_channels: int = 256,
        num_upsample: int = 4,
        num_res_blocks: int = 2,
        dropout: float = 0.0,
    ):
        super().__init__()
        
        self.embedding_dim = embedding_dim
        self.num_upsample = num_upsample
        self.upsample_factor = 2 ** num_upsample
        
        # Channel progression (decreasing as we upsample)
        # e.g., [256, 256, 128, 64, 32] for num_upsample=4
        channels = []
        ch = base_channels
        for i in range(num_upsample + 1):
            channels.append(ch)
            if i >= 1:
                ch = max(32, ch // 2)
                
        # Input projection: embedding_dim → base_channels
        self.input_proj = nn.Conv2d(embedding_dim, channels[0], 1)
        
        # Initial residual blocks at lowest resolution
        self.initial_blocks = nn.ModuleList([
            ResBlock(channels[0], dropout=dropout)
            for _ in range(num_res_blocks)
        ])
        
        # Upsampling blocks
        self.up_blocks = nn.ModuleList()
        for i in range(num_upsample):
            in_ch = channels[i]
            out_ch = channels[i + 1]
            
            block = nn.ModuleDict({
                "upsample": Upsample(in_ch),
                "res_blocks": nn.ModuleList([
                    ResBlock(in_ch if j == 0 else out_ch, out_ch, dropout=dropout)
                    for j in range(num_res_blocks)
                ]),
            })
            self.up_blocks.append(block)
            
        # Final output
        self.final_norm = nn.GroupNorm(32, channels[-1])
        self.final_conv = nn.Conv2d(channels[-1], out_channels, 3, padding=1)
        
    def forward(
        self, 
        z_q: torch.Tensor,
        return_features: bool = False,
    ) -> Tuple[torch.Tensor, Dict[str, Any]]:
        """
        Decode VQ embeddings to image.
        
        Args:
            z_q: [B, H, W, D] quantized embeddings
            return_features: Return intermediate features
            
        Returns:
            images: [B, 3, H*16, W*16] reconstructed images
            info: Dict with features etc.
        """
        features = [] if return_features else None
        
        # Rearrange to [B, D, H, W]
        x = rearrange(z_q, 'b h w d -> b d h w')
        
        # Input projection
        x = self.input_proj(x)
        
        # Initial blocks
        for block in self.initial_blocks:
            x = block(x)
            
        if return_features:
            features.append(x)
            
        # Upsampling
        for up_block in self.up_blocks:
            x = up_block["upsample"](x)
            for res_block in up_block["res_blocks"]:
                x = res_block(x)
                
            if return_features:
                features.append(x)
                
        # Final output
        x = self.final_norm(x)
        x = F.gelu(x)
        x = self.final_conv(x)
        
        # Tanh for [-1, 1] output
        images = torch.tanh(x)
        
        info = {}
        if return_features:
            info["features"] = features
            
        return images, info
    
    def decode_indices(
        self,
        indices: torch.Tensor,
        codebook: nn.Module,
    ) -> torch.Tensor:
        """
        Decode from VQ indices directly.
        
        Args:
            indices: [B, H, W] token indices
            codebook: VQCodebook instance
            
        Returns:
            images: [B, 3, H*16, W*16]
        """
        # Get embeddings from codebook
        z_q = codebook.decode(indices)  # [B, H, W, D]
        
        # Decode to image
        images, _ = self.forward(z_q)
        
        return images


class TransformerVQDecoder(nn.Module):
    """
    Transformer-based decoder (альтернатива CNN).
    
    Использует cross-attention между VQ токенами и pixel queries.
    """
    
    def __init__(
        self,
        embedding_dim: int = 1024,
        hidden_dim: int = 512,
        num_layers: int = 6,
        num_heads: int = 8,
        out_channels: int = 3,
        upsample_factor: int = 16,
    ):
        super().__init__()
        
        self.embedding_dim = embedding_dim
        self.upsample_factor = upsample_factor
        
        # Project VQ embeddings
        self.vq_proj = nn.Linear(embedding_dim, hidden_dim)
        
        # Pixel queries (learnable)
        # For each VQ token, we have upsample_factor^2 pixel queries
        self.pixel_queries = nn.Parameter(
            torch.randn(upsample_factor ** 2, hidden_dim) * 0.02
        )
        
        # Transformer layers
        self.layers = nn.ModuleList([
            nn.TransformerDecoderLayer(
                d_model=hidden_dim,
                nhead=num_heads,
                dim_feedforward=hidden_dim * 4,
                dropout=0.1,
                activation='gelu',
                batch_first=True,
            )
            for _ in range(num_layers)
        ])
        
        # Output projection
        self.output_proj = nn.Sequential(
            nn.LayerNorm(hidden_dim),
            nn.Linear(hidden_dim, out_channels),
        )
        
    def forward(self, z_q: torch.Tensor) -> Tuple[torch.Tensor, Dict[str, Any]]:
        """
        Args:
            z_q: [B, H, W, D] VQ embeddings
        Returns:
            images: [B, 3, H*up, W*up]
        """
        B, H, W, D = z_q.shape
        
        # Flatten VQ embeddings
        z_q_flat = rearrange(z_q, 'b h w d -> b (h w) d')  # [B, H*W, D]
        z_q_proj = self.vq_proj(z_q_flat)  # [B, H*W, hidden]
        
        # Expand pixel queries for each VQ token
        # [up^2, hidden] → [B, H*W*up^2, hidden]
        num_vq = H * W
        pixel_q = self.pixel_queries.unsqueeze(0).unsqueeze(0)  # [1, 1, up^2, hidden]
        pixel_q = pixel_q.expand(B, num_vq, -1, -1)  # [B, H*W, up^2, hidden]
        pixel_q = rearrange(pixel_q, 'b n p h -> b (n p) h')  # [B, H*W*up^2, hidden]
        
        # Memory: VQ embeddings for cross-attention
        memory = z_q_proj  # [B, H*W, hidden]
        
        # Transformer decoder
        x = pixel_q
        for layer in self.layers:
            x = layer(x, memory)
            
        # Output projection
        pixels = self.output_proj(x)  # [B, H*W*up^2, 3]
        
        # Reshape to image
        up = self.upsample_factor
        pixels = rearrange(
            pixels, 
            'b (h w ph pw) c -> b c (h ph) (w pw)',
            h=H, w=W, ph=up, pw=up
        )
        
        images = torch.tanh(pixels)
        
        return images, {}
