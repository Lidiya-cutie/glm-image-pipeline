"""
DiT Decoder Model

7B Diffusion Transformer для финальной генерации изображений.
Принимает семантические VQ токены и текст как условие.

Архитектура: Single-stream DiT (как в CogView4)
- Latent patches + VQ embeddings + text embeddings
- AdaLN conditioning on timestep
- Flow matching или DDPM
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange, repeat
from typing import Optional, Tuple, List, Dict, Any
import math

from .config import DiTConfig


def modulate(x: torch.Tensor, shift: torch.Tensor, scale: torch.Tensor) -> torch.Tensor:
    """Adaptive layer norm modulation."""
    return x * (1 + scale.unsqueeze(1)) + shift.unsqueeze(1)


class TimestepEmbedding(nn.Module):
    """Sinusoidal timestep embeddings."""
    
    def __init__(self, dim: int, max_period: int = 10000):
        super().__init__()
        self.dim = dim
        self.max_period = max_period
        
        half_dim = dim // 2
        freqs = torch.exp(
            -math.log(max_period) * torch.arange(half_dim) / half_dim
        )
        self.register_buffer("freqs", freqs)
        
        # MLP
        self.mlp = nn.Sequential(
            nn.Linear(dim, dim * 4),
            nn.SiLU(),
            nn.Linear(dim * 4, dim),
        )
        
    def forward(self, t: torch.Tensor) -> torch.Tensor:
        """
        Args:
            t: [B] timesteps (0 to 1)
        Returns:
            [B, D] embeddings
        """
        # Sinusoidal encoding
        args = t[:, None] * self.freqs[None, :] * self.max_period
        emb = torch.cat([torch.sin(args), torch.cos(args)], dim=-1)
        
        # MLP
        return self.mlp(emb)


class PatchEmbed(nn.Module):
    """Image to patches."""
    
    def __init__(
        self,
        in_channels: int = 4,
        hidden_size: int = 3072,
        patch_size: int = 2,
    ):
        super().__init__()
        self.patch_size = patch_size
        self.proj = nn.Conv2d(
            in_channels, hidden_size,
            kernel_size=patch_size, stride=patch_size,
        )
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: [B, C, H, W] latent
        Returns:
            [B, N, D] patches
        """
        x = self.proj(x)  # [B, D, H/P, W/P]
        return rearrange(x, 'b d h w -> b (h w) d')


class DiTBlock(nn.Module):
    """
    DiT Transformer block with adaptive layer norm.
    
    Includes:
    - Self-attention
    - Cross-attention to VQ + text conditioning
    - MLP
    - AdaLN modulation from timestep
    """
    
    def __init__(self, config: DiTConfig):
        super().__init__()
        
        hidden_size = config.hidden_size
        num_heads = config.num_heads
        mlp_hidden = config.mlp_hidden_dim
        
        # Self-attention
        self.norm1 = nn.LayerNorm(hidden_size, eps=config.norm_eps, elementwise_affine=False)
        self.attn = nn.MultiheadAttention(
            hidden_size, num_heads,
            dropout=config.attention_dropout,
            batch_first=True,
        )
        
        # Cross-attention to conditioning
        self.norm2 = nn.LayerNorm(hidden_size, eps=config.norm_eps, elementwise_affine=False)
        self.cross_attn = nn.MultiheadAttention(
            hidden_size, num_heads,
            dropout=config.attention_dropout,
            batch_first=True,
        )
        
        # MLP
        self.norm3 = nn.LayerNorm(hidden_size, eps=config.norm_eps, elementwise_affine=False)
        self.mlp = nn.Sequential(
            nn.Linear(hidden_size, mlp_hidden),
            nn.GELU(),
            nn.Dropout(config.mlp_dropout),
            nn.Linear(mlp_hidden, hidden_size),
            nn.Dropout(config.mlp_dropout),
        )
        
        # AdaLN modulation (6 outputs: 2 for each norm)
        self.adaLN_modulation = nn.Sequential(
            nn.SiLU(),
            nn.Linear(hidden_size, hidden_size * 6),
        )
        
    def forward(
        self,
        x: torch.Tensor,
        cond: torch.Tensor,
        t_emb: torch.Tensor,
        cond_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            x: [B, N, D] latent patches
            cond: [B, M, D] conditioning (VQ + text)
            t_emb: [B, D] timestep embedding
            cond_mask: [B, M] conditioning attention mask
        """
        # Get modulation parameters
        shift_msa, scale_msa, shift_cross, scale_cross, shift_mlp, scale_mlp = \
            self.adaLN_modulation(t_emb).chunk(6, dim=-1)
            
        # Self-attention
        x_norm = self.norm1(x)
        x_mod = modulate(x_norm, shift_msa, scale_msa)
        attn_out, _ = self.attn(x_mod, x_mod, x_mod)
        x = x + attn_out
        
        # Cross-attention
        x_norm = self.norm2(x)
        x_mod = modulate(x_norm, shift_cross, scale_cross)
        
        if cond_mask is not None:
            # Convert to attention mask format
            key_padding_mask = ~cond_mask.bool()
        else:
            key_padding_mask = None
            
        cross_out, _ = self.cross_attn(
            x_mod, cond, cond,
            key_padding_mask=key_padding_mask,
        )
        x = x + cross_out
        
        # MLP
        x_norm = self.norm3(x)
        x_mod = modulate(x_norm, shift_mlp, scale_mlp)
        x = x + self.mlp(x_mod)
        
        return x


class FinalLayer(nn.Module):
    """Final layer with AdaLN and linear projection."""
    
    def __init__(self, hidden_size: int, out_channels: int, patch_size: int):
        super().__init__()
        self.norm = nn.LayerNorm(hidden_size, elementwise_affine=False)
        self.linear = nn.Linear(hidden_size, patch_size * patch_size * out_channels)
        self.adaLN_modulation = nn.Sequential(
            nn.SiLU(),
            nn.Linear(hidden_size, hidden_size * 2),
        )
        
    def forward(self, x: torch.Tensor, t_emb: torch.Tensor) -> torch.Tensor:
        shift, scale = self.adaLN_modulation(t_emb).chunk(2, dim=-1)
        x = modulate(self.norm(x), shift, scale)
        return self.linear(x)


class DiTDecoder(nn.Module):
    """
    Diffusion Transformer Decoder.
    
    Генерирует изображение по семантическим VQ токенам и тексту.
    """
    
    def __init__(self, config: DiTConfig):
        super().__init__()
        self.config = config
        
        # Patch embedding
        self.patch_embed = PatchEmbed(
            config.in_channels,
            config.hidden_size,
            config.patch_size,
        )
        
        # Timestep embedding
        self.time_embed = TimestepEmbedding(config.hidden_size)
        
        # VQ conditioning projection
        self.vq_proj = nn.Linear(config.vq_embed_dim, config.hidden_size)
        
        # Text conditioning projection  
        self.text_proj = nn.Linear(config.text_embed_dim, config.hidden_size)
        
        # Positional embeddings for latent patches
        # Will be initialized based on resolution
        self.pos_embed = None
        
        # Positional embeddings for VQ tokens
        self.vq_pos_embed = nn.Parameter(
            torch.randn(1, config.num_vq_tokens, config.hidden_size) * 0.02
        )
        
        # Transformer blocks
        self.blocks = nn.ModuleList([
            DiTBlock(config)
            for _ in range(config.num_layers)
        ])
        
        # Final layer
        self.final_layer = FinalLayer(
            config.hidden_size,
            config.out_channels,
            config.patch_size,
        )
        
        # Initialize
        self._init_weights()
        
    def _init_weights(self):
        """Initialize weights."""
        def _basic_init(module):
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
                    
        self.apply(_basic_init)
        
        # Zero-init final layer
        nn.init.zeros_(self.final_layer.linear.weight)
        nn.init.zeros_(self.final_layer.linear.bias)
        
        # Zero-init AdaLN modulation
        for block in self.blocks:
            nn.init.zeros_(block.adaLN_modulation[-1].weight)
            nn.init.zeros_(block.adaLN_modulation[-1].bias)
            
    def _get_pos_embed(self, h: int, w: int, device: torch.device) -> torch.Tensor:
        """Get 2D positional embeddings for patches."""
        # Sinusoidal 2D
        dim = self.config.hidden_size
        
        y = torch.arange(h, device=device).float()
        x = torch.arange(w, device=device).float()
        y, x = torch.meshgrid(y, x, indexing='ij')
        
        omega = torch.arange(dim // 4, device=device).float()
        omega = 1.0 / (10000 ** (omega / (dim // 4)))
        
        y_emb = y.reshape(-1, 1) * omega
        x_emb = x.reshape(-1, 1) * omega
        
        pos_emb = torch.cat([
            torch.sin(y_emb), torch.cos(y_emb),
            torch.sin(x_emb), torch.cos(x_emb),
        ], dim=-1)
        
        return pos_emb.unsqueeze(0)
    
    def unpatchify(self, x: torch.Tensor, h: int, w: int) -> torch.Tensor:
        """Convert patches back to spatial."""
        p = self.config.patch_size
        c = self.config.out_channels
        
        x = rearrange(
            x, 'b (h w) (p1 p2 c) -> b c (h p1) (w p2)',
            h=h, w=w, p1=p, p2=p, c=c
        )
        return x
    
    def forward(
        self,
        x: torch.Tensor,
        t: torch.Tensor,
        vq_embeddings: torch.Tensor,
        text_embeddings: torch.Tensor,
        vq_mask: Optional[torch.Tensor] = None,
        text_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Forward pass.
        
        Args:
            x: [B, C, H, W] noisy latent
            t: [B] timesteps (normalized 0-1)
            vq_embeddings: [B, N_vq, D_vq] VQ embeddings from codebook
            text_embeddings: [B, N_text, D_text] text embeddings from AR
            vq_mask: [B, N_vq] VQ attention mask
            text_mask: [B, N_text] text attention mask
            
        Returns:
            [B, C, H, W] predicted noise/velocity
        """
        B, C, H, W = x.shape
        
        # Patch embed
        h, w = H // self.config.patch_size, W // self.config.patch_size
        x = self.patch_embed(x)  # [B, h*w, D]
        
        # Add positional embeddings
        pos_emb = self._get_pos_embed(h, w, x.device)
        x = x + pos_emb
        
        # Timestep embedding
        t_emb = self.time_embed(t)  # [B, D]
        
        # Project conditioning
        vq_cond = self.vq_proj(vq_embeddings)  # [B, N_vq, D]
        vq_cond = vq_cond + self.vq_pos_embed[:, :vq_cond.shape[1]]
        
        text_cond = self.text_proj(text_embeddings)  # [B, N_text, D]
        
        # Concatenate conditioning
        cond = torch.cat([vq_cond, text_cond], dim=1)  # [B, N_vq + N_text, D]
        
        # Combine masks
        if vq_mask is not None and text_mask is not None:
            cond_mask = torch.cat([vq_mask, text_mask], dim=1)
        else:
            cond_mask = None
            
        # Transformer blocks
        for block in self.blocks:
            x = block(x, cond, t_emb, cond_mask)
            
        # Final layer
        x = self.final_layer(x, t_emb)  # [B, h*w, p*p*c]
        
        # Unpatchify
        x = self.unpatchify(x, h, w)  # [B, C, H, W]
        
        return x
    
    @torch.no_grad()
    def sample(
        self,
        vq_embeddings: torch.Tensor,
        text_embeddings: torch.Tensor,
        latent_size: Tuple[int, int] = (128, 128),  # H, W in latent space
        num_steps: int = 50,
        cfg_scale: float = 7.5,
        vq_mask: Optional[torch.Tensor] = None,
        text_mask: Optional[torch.Tensor] = None,
        null_text_embeddings: Optional[torch.Tensor] = None,  # For CFG
    ) -> torch.Tensor:
        """
        Sample images using flow matching.
        
        Args:
            vq_embeddings: [B, N_vq, D_vq]
            text_embeddings: [B, N_text, D_text]
            latent_size: (H, W) latent dimensions
            num_steps: Sampling steps
            cfg_scale: CFG guidance scale
            vq_mask, text_mask: Attention masks
            null_text_embeddings: For CFG (unconditional)
            
        Returns:
            [B, C, H, W] sampled latents
        """
        B = vq_embeddings.shape[0]
        device = vq_embeddings.device
        H, W = latent_size
        
        # Initialize noise
        x = torch.randn(B, self.config.in_channels, H, W, device=device)
        
        # Time schedule
        timesteps = torch.linspace(1, 0, num_steps + 1, device=device)
        
        for i in range(num_steps):
            t = timesteps[i].expand(B)
            t_next = timesteps[i + 1].expand(B)
            
            # Predict velocity
            if cfg_scale > 1.0 and null_text_embeddings is not None:
                # CFG: batch conditional and unconditional
                x_double = torch.cat([x, x], dim=0)
                t_double = torch.cat([t, t], dim=0)
                vq_double = torch.cat([vq_embeddings, vq_embeddings], dim=0)
                text_double = torch.cat([text_embeddings, null_text_embeddings], dim=0)
                
                v = self.forward(x_double, t_double, vq_double, text_double)
                v_cond, v_uncond = v.chunk(2, dim=0)
                v = v_uncond + cfg_scale * (v_cond - v_uncond)
            else:
                v = self.forward(x, t, vq_embeddings, text_embeddings, vq_mask, text_mask)
                
            # Euler step
            dt = t_next - t
            x = x + v * dt.view(-1, 1, 1, 1)
            
        return x
    
    def compute_loss(
        self,
        images_latent: torch.Tensor,
        vq_embeddings: torch.Tensor,
        text_embeddings: torch.Tensor,
        vq_mask: Optional[torch.Tensor] = None,
        text_mask: Optional[torch.Tensor] = None,
    ) -> Dict[str, torch.Tensor]:
        """
        Compute training loss (flow matching).
        
        Args:
            images_latent: [B, C, H, W] target latents
            vq_embeddings: [B, N_vq, D_vq]
            text_embeddings: [B, N_text, D_text]
            
        Returns:
            Dict with loss and metrics
        """
        B = images_latent.shape[0]
        device = images_latent.device
        
        # Sample random timesteps
        t = torch.rand(B, device=device)
        
        # Sample noise
        noise = torch.randn_like(images_latent)
        
        # Interpolate (flow matching)
        x_t = t.view(-1, 1, 1, 1) * images_latent + (1 - t.view(-1, 1, 1, 1)) * noise
        
        # Target velocity
        target_v = images_latent - noise
        
        # Predict velocity
        pred_v = self.forward(x_t, t, vq_embeddings, text_embeddings, vq_mask, text_mask)
        
        # MSE loss
        loss = F.mse_loss(pred_v, target_v)
        
        return {
            "loss": loss,
            "mse": loss.detach(),
        }
