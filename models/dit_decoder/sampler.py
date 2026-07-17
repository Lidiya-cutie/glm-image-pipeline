"""
Diffusion Samplers

Различные схемы семплирования для DiT:
- Flow Matching (основной)
- DDPM
- DPM++ variants
"""

import torch
import torch.nn as nn
from typing import Optional, Tuple, Callable, List
import math
from abc import ABC, abstractmethod


class BaseSampler(ABC):
    """Base class for diffusion samplers."""
    
    @abstractmethod
    def sample(
        self,
        model: nn.Module,
        shape: Tuple[int, ...],
        condition: dict,
        num_steps: int,
        cfg_scale: float,
        **kwargs,
    ) -> torch.Tensor:
        """Sample from the model."""
        pass


class FlowMatchingSampler(BaseSampler):
    """
    Flow Matching sampler.
    
    Используется в GLM-Image для DiT.
    """
    
    def __init__(
        self,
        sigma_min: float = 0.002,
        sigma_max: float = 80.0,
    ):
        self.sigma_min = sigma_min
        self.sigma_max = sigma_max
        
    def get_schedule(
        self, 
        num_steps: int, 
        device: torch.device,
        schedule_type: str = "linear",
    ) -> torch.Tensor:
        """Get timestep schedule."""
        if schedule_type == "linear":
            return torch.linspace(1, 0, num_steps + 1, device=device)
        elif schedule_type == "cosine":
            t = torch.linspace(0, 1, num_steps + 1, device=device)
            return 1 - (1 - torch.cos(t * math.pi / 2))
        elif schedule_type == "quadratic":
            t = torch.linspace(0, 1, num_steps + 1, device=device)
            return 1 - t ** 2
        else:
            return torch.linspace(1, 0, num_steps + 1, device=device)
            
    @torch.no_grad()
    def sample(
        self,
        model: nn.Module,
        shape: Tuple[int, ...],
        condition: dict,
        num_steps: int = 50,
        cfg_scale: float = 7.5,
        schedule: str = "linear",
        solver: str = "euler",  # euler, heun
        device: torch.device = None,
        callback: Optional[Callable] = None,
    ) -> torch.Tensor:
        """
        Sample using flow matching.
        
        Args:
            model: DiT model
            shape: (B, C, H, W) output shape
            condition: Dict with vq_embeddings, text_embeddings, masks
            num_steps: Number of sampling steps
            cfg_scale: CFG guidance scale
            schedule: Time schedule type
            solver: ODE solver (euler, heun)
            device: Device to use
            callback: Progress callback
            
        Returns:
            [B, C, H, W] sampled latents
        """
        B, C, H, W = shape
        device = device or next(model.parameters()).device
        
        # Initialize from noise
        x = torch.randn(shape, device=device)
        
        # Get schedule
        timesteps = self.get_schedule(num_steps, device, schedule)
        
        # Extract conditioning
        vq_embeddings = condition["vq_embeddings"]
        text_embeddings = condition["text_embeddings"]
        null_text = condition.get("null_text_embeddings")
        vq_mask = condition.get("vq_mask")
        text_mask = condition.get("text_mask")
        
        # Sampling loop
        for i in range(num_steps):
            t = timesteps[i]
            t_next = timesteps[i + 1]
            t_batch = t.expand(B)
            
            # Get velocity prediction
            if cfg_scale > 1.0 and null_text is not None:
                v = self._cfg_forward(
                    model, x, t_batch,
                    vq_embeddings, text_embeddings, null_text,
                    vq_mask, text_mask, cfg_scale,
                )
            else:
                v = model(x, t_batch, vq_embeddings, text_embeddings, vq_mask, text_mask)
                
            # Solver step
            if solver == "euler":
                dt = t_next - t
                x = x + v * dt
            elif solver == "heun":
                # Heun's method (2nd order)
                dt = t_next - t
                x_pred = x + v * dt
                
                if i < num_steps - 1:
                    t_next_batch = t_next.expand(B)
                    if cfg_scale > 1.0 and null_text is not None:
                        v_next = self._cfg_forward(
                            model, x_pred, t_next_batch,
                            vq_embeddings, text_embeddings, null_text,
                            vq_mask, text_mask, cfg_scale,
                        )
                    else:
                        v_next = model(x_pred, t_next_batch, vq_embeddings, text_embeddings, vq_mask, text_mask)
                    x = x + dt * (v + v_next) / 2
                else:
                    x = x_pred
                    
            if callback is not None:
                callback(i + 1, num_steps, x)
                
        return x
    
    def _cfg_forward(
        self,
        model: nn.Module,
        x: torch.Tensor,
        t: torch.Tensor,
        vq_emb: torch.Tensor,
        text_emb: torch.Tensor,
        null_text: torch.Tensor,
        vq_mask: Optional[torch.Tensor],
        text_mask: Optional[torch.Tensor],
        cfg_scale: float,
    ) -> torch.Tensor:
        """CFG forward pass."""
        B = x.shape[0]
        
        # Batch conditional and unconditional
        x_double = torch.cat([x, x], dim=0)
        t_double = torch.cat([t, t], dim=0)
        vq_double = torch.cat([vq_emb, vq_emb], dim=0)
        text_double = torch.cat([text_emb, null_text], dim=0)
        
        if vq_mask is not None:
            vq_mask = torch.cat([vq_mask, vq_mask], dim=0)
        if text_mask is not None:
            text_mask = torch.cat([text_mask, text_mask], dim=0)
            
        v = model(x_double, t_double, vq_double, text_double, vq_mask, text_mask)
        v_cond, v_uncond = v.chunk(2, dim=0)
        
        return v_uncond + cfg_scale * (v_cond - v_uncond)


class DiffusionSampler(BaseSampler):
    """
    DDPM-style sampler.
    
    Alternative to flow matching.
    """
    
    def __init__(
        self,
        num_timesteps: int = 1000,
        beta_start: float = 0.0001,
        beta_end: float = 0.02,
        beta_schedule: str = "linear",
    ):
        self.num_timesteps = num_timesteps
        
        # Create beta schedule
        if beta_schedule == "linear":
            betas = torch.linspace(beta_start, beta_end, num_timesteps)
        elif beta_schedule == "cosine":
            s = 0.008
            steps = num_timesteps + 1
            x = torch.linspace(0, num_timesteps, steps)
            alphas_cumprod = torch.cos(((x / num_timesteps) + s) / (1 + s) * math.pi * 0.5) ** 2
            alphas_cumprod = alphas_cumprod / alphas_cumprod[0]
            betas = 1 - (alphas_cumprod[1:] / alphas_cumprod[:-1])
            betas = torch.clamp(betas, 0.0001, 0.9999)
        else:
            betas = torch.linspace(beta_start, beta_end, num_timesteps)
            
        self.betas = betas
        self.alphas = 1.0 - betas
        self.alphas_cumprod = torch.cumprod(self.alphas, dim=0)
        self.sqrt_alphas_cumprod = torch.sqrt(self.alphas_cumprod)
        self.sqrt_one_minus_alphas_cumprod = torch.sqrt(1.0 - self.alphas_cumprod)
        
    def _move_to_device(self, device: torch.device):
        """Move buffers to device."""
        self.betas = self.betas.to(device)
        self.alphas = self.alphas.to(device)
        self.alphas_cumprod = self.alphas_cumprod.to(device)
        self.sqrt_alphas_cumprod = self.sqrt_alphas_cumprod.to(device)
        self.sqrt_one_minus_alphas_cumprod = self.sqrt_one_minus_alphas_cumprod.to(device)
        
    @torch.no_grad()
    def sample(
        self,
        model: nn.Module,
        shape: Tuple[int, ...],
        condition: dict,
        num_steps: int = 50,
        cfg_scale: float = 7.5,
        device: torch.device = None,
        callback: Optional[Callable] = None,
    ) -> torch.Tensor:
        """
        Sample using DDPM.
        """
        B, C, H, W = shape
        device = device or next(model.parameters()).device
        self._move_to_device(device)
        
        # Initialize noise
        x = torch.randn(shape, device=device)
        
        # Subsample timesteps
        step_size = self.num_timesteps // num_steps
        timesteps = list(range(0, self.num_timesteps, step_size))[::-1]
        
        vq_emb = condition["vq_embeddings"]
        text_emb = condition["text_embeddings"]
        null_text = condition.get("null_text_embeddings")
        
        for i, t in enumerate(timesteps):
            t_batch = torch.full((B,), t / self.num_timesteps, device=device)
            
            # Predict noise
            if cfg_scale > 1.0 and null_text is not None:
                x_double = torch.cat([x, x], dim=0)
                t_double = torch.cat([t_batch, t_batch], dim=0)
                vq_double = torch.cat([vq_emb, vq_emb], dim=0)
                text_double = torch.cat([text_emb, null_text], dim=0)
                
                eps = model(x_double, t_double, vq_double, text_double)
                eps_cond, eps_uncond = eps.chunk(2, dim=0)
                eps = eps_uncond + cfg_scale * (eps_cond - eps_uncond)
            else:
                eps = model(x, t_batch, vq_emb, text_emb)
                
            # DDPM step
            alpha = self.alphas[t]
            alpha_cumprod = self.alphas_cumprod[t]
            beta = self.betas[t]
            
            # Predicted x0
            x0_pred = (x - self.sqrt_one_minus_alphas_cumprod[t] * eps) / self.sqrt_alphas_cumprod[t]
            x0_pred = torch.clamp(x0_pred, -1, 1)
            
            # Posterior mean
            if t > 0:
                alpha_cumprod_prev = self.alphas_cumprod[t - step_size] if t - step_size >= 0 else torch.tensor(1.0, device=device)
                posterior_mean = (
                    torch.sqrt(alpha_cumprod_prev) * beta / (1 - alpha_cumprod) * x0_pred +
                    torch.sqrt(alpha) * (1 - alpha_cumprod_prev) / (1 - alpha_cumprod) * x
                )
                
                # Add noise
                noise = torch.randn_like(x)
                posterior_variance = beta * (1 - alpha_cumprod_prev) / (1 - alpha_cumprod)
                x = posterior_mean + torch.sqrt(posterior_variance) * noise
            else:
                x = x0_pred
                
            if callback is not None:
                callback(i + 1, len(timesteps), x)
                
        return x


class DPMPPSampler(BaseSampler):
    """
    DPM++ sampler (faster convergence).
    """
    
    def __init__(self, sigma_min: float = 0.002, sigma_max: float = 80.0):
        self.sigma_min = sigma_min
        self.sigma_max = sigma_max
        
    def get_sigmas(self, num_steps: int, device: torch.device) -> torch.Tensor:
        """Get sigma schedule."""
        rho = 7.0  # Karras schedule
        ramp = torch.linspace(0, 1, num_steps + 1, device=device)
        min_inv_rho = self.sigma_min ** (1 / rho)
        max_inv_rho = self.sigma_max ** (1 / rho)
        sigmas = (max_inv_rho + ramp * (min_inv_rho - max_inv_rho)) ** rho
        sigmas[-1] = 0
        return sigmas
    
    @torch.no_grad()
    def sample(
        self,
        model: nn.Module,
        shape: Tuple[int, ...],
        condition: dict,
        num_steps: int = 50,
        cfg_scale: float = 7.5,
        device: torch.device = None,
        callback: Optional[Callable] = None,
    ) -> torch.Tensor:
        """
        Sample using DPM++ 2M.
        """
        B, C, H, W = shape
        device = device or next(model.parameters()).device
        
        sigmas = self.get_sigmas(num_steps, device)
        
        # Initialize
        x = torch.randn(shape, device=device) * sigmas[0]
        
        vq_emb = condition["vq_embeddings"]
        text_emb = condition["text_embeddings"]
        null_text = condition.get("null_text_embeddings")
        
        old_denoised = None
        
        for i in range(num_steps):
            sigma = sigmas[i]
            sigma_next = sigmas[i + 1]
            
            # Convert sigma to t
            t = sigma / self.sigma_max
            t_batch = torch.full((B,), t, device=device)
            
            # Denoise
            if cfg_scale > 1.0 and null_text is not None:
                x_double = torch.cat([x, x], dim=0)
                t_double = torch.cat([t_batch, t_batch], dim=0)
                vq_double = torch.cat([vq_emb, vq_emb], dim=0)
                text_double = torch.cat([text_emb, null_text], dim=0)
                
                out = model(x_double, t_double, vq_double, text_double)
                out_cond, out_uncond = out.chunk(2, dim=0)
                denoised = out_uncond + cfg_scale * (out_cond - out_uncond)
            else:
                denoised = model(x, t_batch, vq_emb, text_emb)
                
            # DPM++ 2M step
            if sigma_next == 0:
                x = denoised
            else:
                if old_denoised is None:
                    # First step: Euler
                    h = torch.log(sigma_next / sigma)
                    x = x + h * (denoised - x) / sigma
                else:
                    # Second-order
                    h = torch.log(sigma_next / sigma)
                    h_last = torch.log(sigma / sigmas[i - 1])
                    r = h_last / h
                    denoised_prime = (1 + r) * denoised - r * old_denoised
                    x = x + h * (denoised_prime - x) / sigma
                    
                old_denoised = denoised
                
            if callback is not None:
                callback(i + 1, num_steps, x)
                
        return x
