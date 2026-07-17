"""
GLM-Image Autoregressive Model

9B параметров, инициализируется из GLM-4-9B.
Генерирует семантические VQ токены по текстовому промпту.

Формат последовательности:
[BOS] text_tokens [IMAGE_START] vq_tokens [IMAGE_END] [EOS]

Для I2I:
[BOS] text_tokens [IMAGE_START] source_vq_tokens [SEP] target_vq_tokens [IMAGE_END] [EOS]
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple, List, Dict, Any, Union
from einops import rearrange
import math

from transformers import PreTrainedModel
from transformers.modeling_outputs import CausalLMOutputWithPast

from .config import GLMImageARConfig
from .generation import ARGenerationMixin


class RMSNorm(nn.Module):
    """RMS Normalization."""
    
    def __init__(self, hidden_size: int, eps: float = 1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(hidden_size))
        self.eps = eps
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        variance = x.pow(2).mean(-1, keepdim=True)
        x = x * torch.rsqrt(variance + self.eps)
        return self.weight * x


class RotaryEmbedding(nn.Module):
    """Rotary Position Embedding (RoPE)."""
    
    def __init__(
        self, 
        dim: int, 
        max_position_embeddings: int = 131072,
        base: float = 10000.0,
    ):
        super().__init__()
        self.dim = dim
        self.max_position_embeddings = max_position_embeddings
        self.base = base
        
        inv_freq = 1.0 / (self.base ** (torch.arange(0, self.dim, 2).float() / self.dim))
        self.register_buffer("inv_freq", inv_freq, persistent=False)
        
        # Build cache
        self._set_cos_sin_cache(max_position_embeddings)
        
    def _set_cos_sin_cache(self, seq_len: int):
        t = torch.arange(seq_len, device=self.inv_freq.device, dtype=self.inv_freq.dtype)
        freqs = torch.outer(t, self.inv_freq)
        emb = torch.cat((freqs, freqs), dim=-1)
        self.register_buffer("cos_cached", emb.cos(), persistent=False)
        self.register_buffer("sin_cached", emb.sin(), persistent=False)
        
    def forward(self, x: torch.Tensor, position_ids: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        # x: [B, num_heads, seq_len, head_dim]
        seq_len = position_ids.max() + 1
        
        if seq_len > self.max_position_embeddings:
            self._set_cos_sin_cache(seq_len)
            
        cos = self.cos_cached[position_ids]  # [B, seq_len, dim]
        sin = self.sin_cached[position_ids]
        
        return cos.unsqueeze(1), sin.unsqueeze(1)


def rotate_half(x: torch.Tensor) -> torch.Tensor:
    """Rotate half for RoPE."""
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat((-x2, x1), dim=-1)


def apply_rotary_pos_emb(
    q: torch.Tensor, 
    k: torch.Tensor, 
    cos: torch.Tensor, 
    sin: torch.Tensor
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Apply rotary positional embeddings."""
    q_embed = (q * cos) + (rotate_half(q) * sin)
    k_embed = (k * cos) + (rotate_half(k) * sin)
    return q_embed, k_embed


class GLMAttention(nn.Module):
    """Multi-head attention with GQA support."""
    
    def __init__(self, config: GLMImageARConfig, layer_idx: int):
        super().__init__()
        self.config = config
        self.layer_idx = layer_idx
        
        self.hidden_size = config.hidden_size
        self.num_heads = config.num_attention_heads
        self.num_kv_heads = config.num_key_value_heads
        self.head_dim = self.hidden_size // self.num_heads
        self.num_key_value_groups = self.num_heads // self.num_kv_heads
        
        self.q_proj = nn.Linear(self.hidden_size, self.num_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(self.hidden_size, self.num_kv_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(self.hidden_size, self.num_kv_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(self.num_heads * self.head_dim, self.hidden_size, bias=False)
        
        self.rotary_emb = RotaryEmbedding(
            self.head_dim,
            max_position_embeddings=config.max_position_embeddings,
            base=config.rope_theta,
        )
        
    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        position_ids: Optional[torch.Tensor] = None,
        past_key_value: Optional[Tuple[torch.Tensor]] = None,
        use_cache: bool = False,
    ) -> Tuple[torch.Tensor, Optional[Tuple[torch.Tensor]]]:
        B, L, _ = hidden_states.shape
        
        # Project
        q = self.q_proj(hidden_states)
        k = self.k_proj(hidden_states)
        v = self.v_proj(hidden_states)
        
        # Reshape
        q = q.view(B, L, self.num_heads, self.head_dim).transpose(1, 2)
        k = k.view(B, L, self.num_kv_heads, self.head_dim).transpose(1, 2)
        v = v.view(B, L, self.num_kv_heads, self.head_dim).transpose(1, 2)
        
        # RoPE
        cos, sin = self.rotary_emb(q, position_ids)
        q, k = apply_rotary_pos_emb(q, k, cos, sin)
        
        # KV cache
        if past_key_value is not None:
            k = torch.cat([past_key_value[0], k], dim=2)
            v = torch.cat([past_key_value[1], v], dim=2)
            
        past_key_value = (k, v) if use_cache else None
        
        # Repeat KV for GQA
        k = k.repeat_interleave(self.num_key_value_groups, dim=1)
        v = v.repeat_interleave(self.num_key_value_groups, dim=1)
        
        # Attention
        attn_weights = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        
        if attention_mask is not None:
            attn_weights = attn_weights + attention_mask
            
        attn_weights = F.softmax(attn_weights, dim=-1, dtype=torch.float32).to(q.dtype)
        attn_output = torch.matmul(attn_weights, v)
        
        # Reshape and project
        attn_output = attn_output.transpose(1, 2).contiguous()
        attn_output = attn_output.view(B, L, self.hidden_size)
        attn_output = self.o_proj(attn_output)
        
        return attn_output, past_key_value


class GLMMLP(nn.Module):
    """GLM MLP with SwiGLU activation."""
    
    def __init__(self, config: GLMImageARConfig):
        super().__init__()
        self.hidden_size = config.hidden_size
        self.intermediate_size = config.intermediate_size
        
        self.gate_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=False)
        self.up_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=False)
        self.down_proj = nn.Linear(self.intermediate_size, self.hidden_size, bias=False)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.down_proj(F.silu(self.gate_proj(x)) * self.up_proj(x))


class GLMDecoderLayer(nn.Module):
    """GLM Transformer decoder layer."""
    
    def __init__(self, config: GLMImageARConfig, layer_idx: int):
        super().__init__()
        self.self_attn = GLMAttention(config, layer_idx)
        self.mlp = GLMMLP(config)
        self.input_layernorm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.post_attention_layernorm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        
    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        position_ids: Optional[torch.Tensor] = None,
        past_key_value: Optional[Tuple[torch.Tensor]] = None,
        use_cache: bool = False,
    ) -> Tuple[torch.Tensor, Optional[Tuple[torch.Tensor]]]:
        # Self attention
        residual = hidden_states
        hidden_states = self.input_layernorm(hidden_states)
        hidden_states, past_key_value = self.self_attn(
            hidden_states,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_value=past_key_value,
            use_cache=use_cache,
        )
        hidden_states = residual + hidden_states
        
        # MLP
        residual = hidden_states
        hidden_states = self.post_attention_layernorm(hidden_states)
        hidden_states = self.mlp(hidden_states)
        hidden_states = residual + hidden_states
        
        return hidden_states, past_key_value


class GLMImageARModel(ARGenerationMixin, PreTrainedModel):
    """
    GLM-Image Autoregressive Model.
    
    Генерирует семантические VQ токены по текстовому промпту.
    """
    
    config_class = GLMImageARConfig
    base_model_prefix = "model"
    
    def __init__(self, config: GLMImageARConfig):
        super().__init__(config)
        self.config = config
        
        # Token embeddings (text + VQ)
        self.embed_tokens = nn.Embedding(config.total_vocab_size, config.hidden_size)
        
        # Optional: separate VQ embedding projection
        # Если VQ embedding dim != hidden size
        if config.vq_embedding_dim != config.hidden_size:
            self.vq_projection = nn.Linear(config.vq_embedding_dim, config.hidden_size)
        else:
            self.vq_projection = None
            
        # Transformer layers
        self.layers = nn.ModuleList([
            GLMDecoderLayer(config, layer_idx)
            for layer_idx in range(config.num_hidden_layers)
        ])
        
        # Final norm
        self.norm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        
        # LM head
        self.lm_head = nn.Linear(config.hidden_size, config.total_vocab_size, bias=False)
        
        # Gradient checkpointing
        self.gradient_checkpointing = config.gradient_checkpointing
        
        # Initialize weights
        self.post_init()
        
    def get_input_embeddings(self) -> nn.Embedding:
        return self.embed_tokens
    
    def set_input_embeddings(self, value: nn.Embedding):
        self.embed_tokens = value
        
    def _prepare_attention_mask(
        self,
        attention_mask: torch.Tensor,
        input_shape: Tuple[int, int],
        past_key_values_length: int,
    ) -> torch.Tensor:
        """Prepare causal attention mask."""
        batch_size, seq_length = input_shape
        
        # Create causal mask
        causal_mask = torch.triu(
            torch.full((seq_length, seq_length), float("-inf"), device=attention_mask.device),
            diagonal=1,
        )
        
        # Expand for batch and heads
        causal_mask = causal_mask.unsqueeze(0).unsqueeze(0)
        
        # Handle past_key_values
        if past_key_values_length > 0:
            causal_mask = torch.cat([
                torch.zeros(1, 1, seq_length, past_key_values_length, device=attention_mask.device),
                causal_mask,
            ], dim=-1)
            
        # Combine with attention mask (for padding)
        if attention_mask is not None:
            # [B, L] -> [B, 1, 1, L]
            expanded_mask = attention_mask[:, None, None, :]
            expanded_mask = (1.0 - expanded_mask) * float("-inf")
            
            # Extend for past
            if past_key_values_length > 0:
                past_mask = torch.zeros(
                    batch_size, 1, 1, past_key_values_length,
                    device=attention_mask.device
                )
                expanded_mask = torch.cat([past_mask, expanded_mask], dim=-1)
                
            causal_mask = causal_mask + expanded_mask
            
        return causal_mask
    
    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        position_ids: Optional[torch.Tensor] = None,
        past_key_values: Optional[List[Tuple[torch.Tensor]]] = None,
        inputs_embeds: Optional[torch.Tensor] = None,
        labels: Optional[torch.Tensor] = None,
        use_cache: bool = True,
        output_hidden_states: bool = False,
        return_dict: bool = True,
        vq_weight_mask: Optional[torch.Tensor] = None,  # For weighted loss on VQ tokens
    ) -> Union[Tuple, CausalLMOutputWithPast]:
        """
        Forward pass.
        
        Args:
            input_ids: [B, L] token IDs
            attention_mask: [B, L] attention mask
            position_ids: [B, L] position IDs
            past_key_values: KV cache
            inputs_embeds: Pre-computed embeddings
            labels: [B, L] labels for loss computation
            use_cache: Use KV cache
            output_hidden_states: Output all hidden states
            return_dict: Return dict or tuple
            vq_weight_mask: [B, L] weights for VQ tokens (for layout emphasis)
        """
        batch_size, seq_length = input_ids.shape
        
        past_key_values_length = 0
        if past_key_values is not None:
            past_key_values_length = past_key_values[0][0].shape[2]
            
        # Position IDs
        if position_ids is None:
            position_ids = torch.arange(
                past_key_values_length,
                seq_length + past_key_values_length,
                device=input_ids.device,
            )
            position_ids = position_ids.unsqueeze(0).expand(batch_size, -1)
            
        # Embeddings
        if inputs_embeds is None:
            inputs_embeds = self.embed_tokens(input_ids)
            
        # Attention mask
        if attention_mask is None:
            attention_mask = torch.ones(batch_size, seq_length, device=input_ids.device)
            
        attention_mask = self._prepare_attention_mask(
            attention_mask,
            (batch_size, seq_length),
            past_key_values_length,
        )
        
        # Forward through layers
        hidden_states = inputs_embeds
        all_hidden_states = () if output_hidden_states else None
        next_cache = () if use_cache else None
        
        for idx, layer in enumerate(self.layers):
            if output_hidden_states:
                all_hidden_states += (hidden_states,)
                
            past_kv = past_key_values[idx] if past_key_values is not None else None
            
            if self.gradient_checkpointing and self.training:
                hidden_states, past_kv = torch.utils.checkpoint.checkpoint(
                    layer,
                    hidden_states,
                    attention_mask,
                    position_ids,
                    past_kv,
                    use_cache,
                )
            else:
                hidden_states, past_kv = layer(
                    hidden_states,
                    attention_mask=attention_mask,
                    position_ids=position_ids,
                    past_key_value=past_kv,
                    use_cache=use_cache,
                )
                
            if use_cache:
                next_cache += (past_kv,)
                
        # Final norm
        hidden_states = self.norm(hidden_states)
        
        if output_hidden_states:
            all_hidden_states += (hidden_states,)
            
        # LM head
        logits = self.lm_head(hidden_states)
        
        # Compute loss
        loss = None
        if labels is not None:
            shift_logits = logits[..., :-1, :].contiguous()
            shift_labels = labels[..., 1:].contiguous()
            
            # Cross entropy
            loss_fct = nn.CrossEntropyLoss(reduction='none')
            loss = loss_fct(
                shift_logits.view(-1, self.config.total_vocab_size),
                shift_labels.view(-1),
            )
            
            # Apply VQ weight mask (for emphasizing layout tokens)
            if vq_weight_mask is not None:
                shift_weights = vq_weight_mask[..., 1:].contiguous().view(-1)
                loss = loss * shift_weights
                loss = loss.sum() / shift_weights.sum()
            else:
                loss = loss.mean()
                
        if not return_dict:
            output = (logits, next_cache, all_hidden_states)
            return (loss,) + output if loss is not None else output
            
        return CausalLMOutputWithPast(
            loss=loss,
            logits=logits,
            past_key_values=next_cache,
            hidden_states=all_hidden_states,
        )
    
    @torch.no_grad()
    def generate_vq_tokens(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        max_new_tokens: int = 4096,
        temperature: float = 0.9,
        top_p: float = 0.95,
        top_k: int = 50,
        do_sample: bool = True,
        stop_token_id: Optional[int] = None,
    ) -> torch.Tensor:
        """
        Generate VQ tokens autoregressively.
        
        Args:
            input_ids: [B, L] text tokens with IMAGE_START
            attention_mask: [B, L]
            max_new_tokens: Max VQ tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling
            top_k: Top-k sampling
            do_sample: Use sampling vs greedy
            stop_token_id: Stop at this token (IMAGE_END)
            
        Returns:
            generated: [B, L + N] full sequence with VQ tokens
        """
        stop_token_id = stop_token_id or self.config.image_end_id
        batch_size = input_ids.shape[0]
        device = input_ids.device
        
        # Initialize
        generated = input_ids.clone()
        past_key_values = None
        
        if attention_mask is None:
            attention_mask = torch.ones_like(input_ids)
            
        for _ in range(max_new_tokens):
            # Forward
            if past_key_values is None:
                model_input = generated
            else:
                model_input = generated[:, -1:]
                
            outputs = self.forward(
                input_ids=model_input,
                attention_mask=attention_mask,
                past_key_values=past_key_values,
                use_cache=True,
            )
            
            logits = outputs.logits[:, -1, :]  # [B, V]
            past_key_values = outputs.past_key_values
            
            # Mask to only VQ tokens during image generation
            # (optional - можно разрешить все токены)
            
            # Sample
            if do_sample:
                # Temperature
                logits = logits / temperature
                
                # Top-k
                if top_k > 0:
                    top_k_logits, top_k_indices = torch.topk(logits, top_k, dim=-1)
                    logits = torch.full_like(logits, float('-inf'))
                    logits.scatter_(-1, top_k_indices, top_k_logits)
                    
                # Top-p
                if top_p < 1.0:
                    sorted_logits, sorted_indices = torch.sort(logits, descending=True)
                    cumulative_probs = torch.cumsum(F.softmax(sorted_logits, dim=-1), dim=-1)
                    
                    # Remove tokens with cumulative prob > top_p
                    sorted_indices_to_remove = cumulative_probs > top_p
                    sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
                    sorted_indices_to_remove[..., 0] = 0
                    
                    indices_to_remove = sorted_indices_to_remove.scatter(
                        -1, sorted_indices, sorted_indices_to_remove
                    )
                    logits[indices_to_remove] = float('-inf')
                    
                # Sample
                probs = F.softmax(logits, dim=-1)
                next_token = torch.multinomial(probs, num_samples=1)
            else:
                next_token = torch.argmax(logits, dim=-1, keepdim=True)
                
            # Append
            generated = torch.cat([generated, next_token], dim=1)
            attention_mask = torch.cat([
                attention_mask,
                torch.ones(batch_size, 1, device=device),
            ], dim=1)
            
            # Check stop condition
            if (next_token == stop_token_id).all():
                break
                
        return generated
    
    @classmethod
    def from_glm4(
        cls, 
        glm4_path: str,
        config: Optional[GLMImageARConfig] = None,
    ) -> "GLMImageARModel":
        """
        Initialize from GLM-4 checkpoint.
        
        Args:
            glm4_path: Path to GLM-4 checkpoint
            config: Optional config override
        """
        from transformers import AutoModelForCausalLM
        
        # Load GLM-4
        glm4 = AutoModelForCausalLM.from_pretrained(
            glm4_path,
            trust_remote_code=True,
        )
        
        # Create config
        if config is None:
            config = GLMImageARConfig()
            
        # Create model
        model = cls(config)
        
        # Copy weights (text embeddings and transformer)
        # Note: VQ embeddings are initialized randomly
        state_dict = glm4.state_dict()
        
        # Map keys
        new_state_dict = {}
        for k, v in state_dict.items():
            if "embed_tokens" in k:
                # Only copy text vocabulary part
                if v.shape[0] > config.text_vocab_size:
                    v = v[:config.text_vocab_size]
            new_state_dict[k] = v
            
        # Load with strict=False to allow new VQ tokens
        model.load_state_dict(new_state_dict, strict=False)
        
        return model
