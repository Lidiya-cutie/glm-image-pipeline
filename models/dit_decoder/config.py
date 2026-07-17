"""
DiT Decoder Configuration

Конфигурация для Diffusion Transformer декодера.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Tuple


@dataclass
class DiTConfig:
    """
    Configuration for DiT Decoder.
    
    7B параметров single-stream DiT.
    """
    
    # Model dimensions
    hidden_size: int = 3072
    num_layers: int = 32
    num_heads: int = 24
    mlp_ratio: float = 4.0
    
    # Input/output
    in_channels: int = 4  # VAE latent channels
    out_channels: int = 4
    patch_size: int = 2  # Patch size in latent space
    
    # Conditioning
    text_embed_dim: int = 4096  # From AR model
    vq_embed_dim: int = 1024   # VQ embedding dim
    num_vq_tokens: int = 4096  # Max VQ tokens (64x64)
    
    # Timestep embedding
    time_embed_dim: int = 256
    
    # Positional encoding
    pos_embed_type: str = "rope_2d"  # rope_2d, sinusoidal, learned
    max_resolution: int = 2048  # Max image resolution
    
    # Attention
    qkv_bias: bool = True
    attention_dropout: float = 0.0
    mlp_dropout: float = 0.0
    
    # Diffusion
    diffusion_type: str = "flow_matching"  # flow_matching, ddpm
    num_timesteps: int = 1000
    sigma_min: float = 0.002
    sigma_max: float = 80.0
    
    # Sampling defaults
    default_num_steps: int = 50
    default_cfg_scale: float = 7.5
    
    # Architecture variants
    use_flash_attention: bool = True
    gradient_checkpointing: bool = False
    
    # Normalization
    norm_type: str = "ada_ln"  # ada_ln (adaptive), rms, layer
    norm_eps: float = 1e-6
    
    @property
    def head_dim(self) -> int:
        return self.hidden_size // self.num_heads
    
    @property
    def mlp_hidden_dim(self) -> int:
        return int(self.hidden_size * self.mlp_ratio)


def get_dit_config_7b() -> DiTConfig:
    """Get 7B DiT configuration."""
    return DiTConfig(
        hidden_size=3072,
        num_layers=32,
        num_heads=24,
    )


def get_dit_config_3b() -> DiTConfig:
    """Get 3B DiT configuration (smaller for testing)."""
    return DiTConfig(
        hidden_size=2048,
        num_layers=24,
        num_heads=16,
    )


def get_dit_config_tiny() -> DiTConfig:
    """Tiny DiT config for smoke/mock without OOM."""
    return DiTConfig(
        hidden_size=256,
        num_layers=2,
        num_heads=4,
        text_embed_dim=256,
        vq_embed_dim=1024,
        num_vq_tokens=256,
    )
