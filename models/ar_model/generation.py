"""
AR Generation Utilities

Расширенные функции генерации для AR модели.
"""

import torch
import torch.nn.functional as F
from typing import Optional, Tuple, List, Dict, Any, Union, Callable
from dataclasses import dataclass
import math


@dataclass
class GenerationConfig:
    """Configuration for VQ token generation."""
    
    # Target resolution and grid
    resolution: Tuple[int, int] = (1024, 1024)  # (H, W)
    patch_size: int = 16
    
    # Sampling parameters
    temperature: float = 0.9
    top_p: float = 0.95
    top_k: int = 50
    do_sample: bool = True
    
    # Stopping
    max_vq_tokens: Optional[int] = None  # Auto-computed from resolution
    
    # Special tokens
    image_start_id: int = 135000
    image_end_id: int = 135001
    vq_offset: int = 135168
    
    # CFG (Classifier-Free Guidance)
    cfg_scale: float = 1.0  # 1.0 = no guidance
    
    # Batch processing
    num_return_sequences: int = 1
    
    @property
    def grid_size(self) -> Tuple[int, int]:
        """Grid size (H/P, W/P)."""
        return (self.resolution[0] // self.patch_size,
                self.resolution[1] // self.patch_size)
    
    @property
    def num_tokens(self) -> int:
        """Total VQ tokens."""
        h, w = self.grid_size
        return h * w
    
    def get_max_vq_tokens(self) -> int:
        """Get max VQ tokens."""
        return self.max_vq_tokens or self.num_tokens


class ARGenerationMixin:
    """
    Mixin class for generation utilities.
    
    Добавляется к GLMImageARModel.
    """
    
    @torch.no_grad()
    def generate_image_tokens(
        self,
        text_input_ids: torch.Tensor,
        text_attention_mask: Optional[torch.Tensor] = None,
        generation_config: Optional[GenerationConfig] = None,
        source_vq_tokens: Optional[torch.Tensor] = None,  # For I2I
        logits_processor: Optional[Callable] = None,
        callback: Optional[Callable] = None,  # Progress callback
    ) -> Dict[str, torch.Tensor]:
        """
        Generate VQ tokens from text prompt.
        
        Args:
            text_input_ids: [B, L] text token IDs
            text_attention_mask: [B, L]
            generation_config: Generation parameters
            source_vq_tokens: [B, N] source VQ tokens for I2I
            logits_processor: Custom logits processing
            callback: Called after each token with (step, total, tokens)
            
        Returns:
            Dict with:
                - "vq_tokens": [B, H, W] generated VQ indices
                - "vq_sequence": [B, N] flat VQ token IDs
                - "full_sequence": [B, L+N+2] full sequence
        """
        config = generation_config or GenerationConfig()
        device = text_input_ids.device
        batch_size = text_input_ids.shape[0]
        
        # Build input sequence
        # [BOS] text_tokens [IMAGE_START] ...
        image_start = torch.full(
            (batch_size, 1), config.image_start_id, 
            device=device, dtype=torch.long
        )
        
        if source_vq_tokens is not None:
            # I2I: add source tokens
            source_seq = source_vq_tokens.view(batch_size, -1) + config.vq_offset
            sep = torch.full((batch_size, 1), self.config.eos_token_id, device=device, dtype=torch.long)
            input_ids = torch.cat([text_input_ids, image_start, source_seq, sep], dim=1)
        else:
            # T2I: just text + image_start
            input_ids = torch.cat([text_input_ids, image_start], dim=1)
            
        if text_attention_mask is None:
            attention_mask = torch.ones_like(input_ids)
        else:
            new_mask = torch.ones(batch_size, input_ids.shape[1] - text_input_ids.shape[1], device=device)
            attention_mask = torch.cat([text_attention_mask, new_mask], dim=1)
            
        # Generate (full-sequence forward: KV-cache path has mask bugs on growing seq)
        max_tokens = config.get_max_vq_tokens()
        generated_tokens = []
        
        for step in range(max_tokens):
            outputs = self.forward(
                input_ids=input_ids,
                attention_mask=attention_mask,
                use_cache=False,
            )
            
            logits = outputs.logits[:, -1, :]  # [B, V]
            
            # Apply logits processor
            if logits_processor is not None:
                logits = logits_processor(input_ids, logits)
                
            # Restrict to VQ vocabulary
            vq_logits = logits[:, config.vq_offset:config.vq_offset + self.config.vq_vocab_size]
            
            # Sample
            next_token = self._sample_token(
                vq_logits, 
                config.temperature,
                config.top_p,
                config.top_k,
                config.do_sample,
            )
            
            # Add offset to get actual token ID
            next_token_id = next_token + config.vq_offset
            
            # Append
            input_ids = torch.cat([input_ids, next_token_id.unsqueeze(1)], dim=1)
            attention_mask = torch.cat([
                attention_mask,
                torch.ones(batch_size, 1, device=device),
            ], dim=1)
            
            generated_tokens.append(next_token)
            
            # Callback
            if callback is not None:
                callback(step + 1, max_tokens, next_token)
                
        # Stack generated tokens
        vq_sequence = torch.stack(generated_tokens, dim=1)  # [B, N]
        
        # Reshape to grid
        h, w = config.grid_size
        vq_tokens = vq_sequence.view(batch_size, h, w)
        
        # Add IMAGE_END
        image_end = torch.full((batch_size, 1), config.image_end_id, device=device, dtype=torch.long)
        full_sequence = torch.cat([input_ids, image_end], dim=1)
        
        return {
            "vq_tokens": vq_tokens,
            "vq_sequence": vq_sequence,
            "full_sequence": full_sequence,
            "grid_size": (h, w),
        }
    
    def _sample_token(
        self,
        logits: torch.Tensor,
        temperature: float,
        top_p: float,
        top_k: int,
        do_sample: bool,
    ) -> torch.Tensor:
        """Sample next token from logits."""
        if not do_sample:
            return torch.argmax(logits, dim=-1)
            
        # Temperature
        logits = logits / temperature
        
        # Top-k
        if top_k > 0 and top_k < logits.shape[-1]:
            top_k_logits, top_k_indices = torch.topk(logits, top_k, dim=-1)
            logits = torch.full_like(logits, float('-inf'))
            logits.scatter_(-1, top_k_indices, top_k_logits)
            
        # Top-p
        if top_p < 1.0:
            sorted_logits, sorted_indices = torch.sort(logits, descending=True)
            cumulative_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
            
            sorted_indices_to_remove = cumulative_probs > top_p
            sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
            sorted_indices_to_remove[..., 0] = 0
            
            indices_to_remove = sorted_indices_to_remove.scatter(
                -1, sorted_indices, sorted_indices_to_remove
            )
            logits[indices_to_remove] = float('-inf')
            
        # Sample
        logits = torch.nan_to_num(logits, nan=-1e4, posinf=1e4, neginf=-1e4)
        probs = F.softmax(logits, dim=-1)
        probs = torch.nan_to_num(probs, nan=0.0, posinf=0.0, neginf=0.0)
        probs = probs.clamp_min(0)
        row_sum = probs.sum(dim=-1, keepdim=True)
        bad = (row_sum <= 0).squeeze(-1)
        if bad.any():
            fallback = torch.argmax(logits, dim=-1)
            probs = probs / row_sum.clamp_min(1e-12)
            sampled = torch.multinomial(probs, num_samples=1).squeeze(-1)
            sampled = torch.where(bad, fallback, sampled)
            return sampled
        probs = probs / row_sum
        return torch.multinomial(probs, num_samples=1).squeeze(-1)
    
    @torch.no_grad()
    def generate_with_cfg(
        self,
        text_input_ids: torch.Tensor,
        null_input_ids: torch.Tensor,  # Unconditional input
        generation_config: Optional[GenerationConfig] = None,
    ) -> Dict[str, torch.Tensor]:
        """
        Generate with Classifier-Free Guidance.
        
        Args:
            text_input_ids: Conditional text tokens
            null_input_ids: Unconditional tokens (empty prompt)
            generation_config: Generation parameters
            
        Returns:
            Same as generate_image_tokens
        """
        config = generation_config or GenerationConfig()
        
        if config.cfg_scale == 1.0:
            # No guidance, normal generation
            return self.generate_image_tokens(text_input_ids, generation_config=config)
            
        device = text_input_ids.device
        batch_size = text_input_ids.shape[0]
        
        # Build inputs for both conditional and unconditional
        image_start = torch.full((batch_size, 1), config.image_start_id, device=device, dtype=torch.long)
        
        cond_input = torch.cat([text_input_ids, image_start], dim=1)
        uncond_input = torch.cat([null_input_ids, image_start], dim=1)
        
        # Batch together
        combined_input = torch.cat([cond_input, uncond_input], dim=0)  # [2B, L]
        
        max_tokens = config.get_max_vq_tokens()
        generated_tokens = []
        past_key_values = None
        
        for step in range(max_tokens):
            if past_key_values is None:
                model_input = combined_input
            else:
                model_input = combined_input[:, -1:]
                
            outputs = self.forward(
                input_ids=model_input,
                past_key_values=past_key_values,
                use_cache=True,
            )
            
            logits = outputs.logits[:, -1, :]
            past_key_values = outputs.past_key_values
            
            # Split conditional and unconditional
            cond_logits, uncond_logits = logits.chunk(2, dim=0)
            
            # CFG
            vq_cond = cond_logits[:, config.vq_offset:config.vq_offset + self.config.vq_vocab_size]
            vq_uncond = uncond_logits[:, config.vq_offset:config.vq_offset + self.config.vq_vocab_size]
            
            guided_logits = uncond_logits + config.cfg_scale * (vq_cond - vq_uncond)
            
            # Sample from conditional
            next_token = self._sample_token(
                guided_logits,
                config.temperature,
                config.top_p,
                config.top_k,
                config.do_sample,
            )
            
            next_token_id = next_token + config.vq_offset
            
            # Update both streams
            next_combined = next_token_id.repeat(2, 1)
            combined_input = torch.cat([combined_input, next_combined.unsqueeze(1)], dim=1)
            
            generated_tokens.append(next_token)
            
        # Process results
        vq_sequence = torch.stack(generated_tokens, dim=1)
        h, w = config.grid_size
        vq_tokens = vq_sequence.view(batch_size, h, w)
        
        return {
            "vq_tokens": vq_tokens,
            "vq_sequence": vq_sequence,
            "grid_size": (h, w),
        }


def create_layout_weight_mask(
    sequence_length: int,
    text_length: int,
    num_layout_tokens: int = 256,
    layout_weight: float = 2.0,
    device: torch.device = None,
) -> torch.Tensor:
    """
    Create weight mask that emphasizes layout tokens.
    
    GLM-Image uses higher weight for first VQ tokens (layout).
    
    Args:
        sequence_length: Total sequence length
        text_length: Length of text portion
        num_layout_tokens: Number of initial VQ tokens to weight higher
        layout_weight: Weight multiplier for layout tokens
        
    Returns:
        [L] weight mask
    """
    weights = torch.ones(sequence_length, device=device)
    
    # VQ tokens start after text + IMAGE_START
    vq_start = text_length + 1
    vq_end = min(vq_start + num_layout_tokens, sequence_length)
    
    weights[vq_start:vq_end] = layout_weight
    
    return weights
