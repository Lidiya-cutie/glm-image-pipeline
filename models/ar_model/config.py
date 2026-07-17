"""
GLM-Image AR Model Configuration

Расширяет GLM-4 config для мультимодального text + image generation.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from transformers import PretrainedConfig


@dataclass
class VQVocabConfig:
    """VQ vocabulary configuration."""
    start_id: int = 135168  # После текстовых токенов GLM-4
    size: int = 16384  # Размер VQ кодбука
    embedding_dim: int = 1024
    
    @property
    def end_id(self) -> int:
        return self.start_id + self.size


@dataclass  
class SpecialTokensConfig:
    """Special tokens for image generation."""
    bos_token_id: int = 1
    eos_token_id: int = 2
    pad_token_id: int = 0
    image_start_id: int = 135000
    image_end_id: int = 135001
    row_separator_id: int = 135002


class GLMImageARConfig(PretrainedConfig):
    """
    Configuration for GLM-Image AR Model.
    
    Extends GLM-4 architecture with VQ vocabulary.
    """
    
    model_type = "glm-image-ar"
    
    def __init__(
        self,
        # GLM-4 base config
        hidden_size: int = 4096,
        intermediate_size: int = 13696,
        num_hidden_layers: int = 40,
        num_attention_heads: int = 32,
        num_key_value_heads: int = 8,  # GQA
        hidden_act: str = "silu",
        max_position_embeddings: int = 131072,
        initializer_range: float = 0.02,
        rms_norm_eps: float = 1e-5,
        use_cache: bool = True,
        rope_theta: float = 10000.0,
        attention_dropout: float = 0.0,
        
        # Extended vocabulary
        text_vocab_size: int = 151552,  # Original GLM-4 vocab
        vq_vocab_start: int = 135168,
        vq_vocab_size: int = 16384,
        
        # VQ embeddings
        vq_embedding_dim: int = 1024,
        tie_vq_embeddings: bool = False,  # Tie input/output VQ embeddings
        
        # Special tokens
        bos_token_id: int = 1,
        eos_token_id: int = 2,
        pad_token_id: int = 0,
        image_start_id: int = 135000,
        image_end_id: int = 135001,
        
        # Generation
        max_vq_tokens: int = 4096,  # 64x64 grid
        default_temperature: float = 0.9,
        default_top_p: float = 0.95,
        default_top_k: int = 50,
        
        # Architecture variants
        use_flash_attention: bool = True,
        gradient_checkpointing: bool = False,
        
        **kwargs,
    ):
        self.hidden_size = hidden_size
        self.intermediate_size = intermediate_size
        self.num_hidden_layers = num_hidden_layers
        self.num_attention_heads = num_attention_heads
        self.num_key_value_heads = num_key_value_heads
        self.hidden_act = hidden_act
        self.max_position_embeddings = max_position_embeddings
        self.initializer_range = initializer_range
        self.rms_norm_eps = rms_norm_eps
        self.use_cache = use_cache
        self.rope_theta = rope_theta
        self.attention_dropout = attention_dropout
        
        # Vocabulary
        self.text_vocab_size = text_vocab_size
        self.vq_vocab_start = vq_vocab_start
        self.vq_vocab_size = vq_vocab_size
        self.total_vocab_size = max(text_vocab_size, vq_vocab_start + vq_vocab_size)
        
        # VQ
        self.vq_embedding_dim = vq_embedding_dim
        self.tie_vq_embeddings = tie_vq_embeddings
        
        # Special tokens
        self.bos_token_id = bos_token_id
        self.eos_token_id = eos_token_id
        self.pad_token_id = pad_token_id
        self.image_start_id = image_start_id
        self.image_end_id = image_end_id
        
        # Generation
        self.max_vq_tokens = max_vq_tokens
        self.default_temperature = default_temperature
        self.default_top_p = default_top_p
        self.default_top_k = default_top_k
        
        # Architecture
        self.use_flash_attention = use_flash_attention
        self.gradient_checkpointing = gradient_checkpointing
        
        super().__init__(
            pad_token_id=pad_token_id,
            bos_token_id=bos_token_id,
            eos_token_id=eos_token_id,
            **kwargs,
        )
        
    @property
    def vocab_size(self) -> int:
        """Total vocabulary size."""
        return self.total_vocab_size
    
    def get_vq_token_id(self, vq_index: int) -> int:
        """Convert VQ codebook index to token ID."""
        return self.vq_vocab_start + vq_index
    
    def get_vq_index(self, token_id: int) -> int:
        """Convert token ID to VQ codebook index."""
        return token_id - self.vq_vocab_start
    
    def is_vq_token(self, token_id: int) -> bool:
        """Check if token is a VQ token."""
        return self.vq_vocab_start <= token_id < self.vq_vocab_start + self.vq_vocab_size
    
    def is_image_special_token(self, token_id: int) -> bool:
        """Check if token is image special token."""
        return token_id in (self.image_start_id, self.image_end_id)


# Preset configurations
def get_ar_config_9b() -> GLMImageARConfig:
    """Get 9B AR model configuration."""
    return GLMImageARConfig(
        hidden_size=4096,
        intermediate_size=13696,
        num_hidden_layers=40,
        num_attention_heads=32,
        num_key_value_heads=8,
    )


def get_ar_config_2b() -> GLMImageARConfig:
    """Get 2B AR model configuration (smaller for testing)."""
    return GLMImageARConfig(
        hidden_size=2048,
        intermediate_size=5504,
        num_hidden_layers=24,
        num_attention_heads=16,
        num_key_value_heads=4,
    )


def get_ar_config_tiny() -> GLMImageARConfig:
    """Tiny AR config for smoke/mock without OOM."""
    return GLMImageARConfig(
        hidden_size=256,
        intermediate_size=512,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        max_position_embeddings=4096,
        text_vocab_size=2048,
        vq_vocab_start=2048,
        vq_vocab_size=256,
        image_start_id=2000,
        image_end_id=2001,
    )
