"""
Complete Semantic VQ Model

Объединяет encoder, codebook и decoder для:
1. Обучения VQ encoder
2. Кодирования изображений в токены (для AR модели)
3. Декодирования токенов обратно в изображения (для валидации)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange
from typing import Tuple, Optional, Dict, Any, List
import math
from omegaconf import DictConfig

from .encoder import SemanticVQEncoder, ConvSemanticEncoder
from .decoder import SemanticVQDecoder, TransformerVQDecoder
from .codebook import VQCodebook, HierarchicalVQCodebook


class SemanticVQModel(nn.Module):
    """
    Full Semantic VQ Model.
    
    Image → Encoder → VQ Codebook → Decoder → Reconstructed Image
    
    При инференсе используется только encoder + codebook.
    Decoder нужен только при обучении для реконструкции.
    """
    
    def __init__(
        self,
        # Encoder config
        encoder_type: str = "vit",
        backbone: str = "vit_large_patch16_384",
        freeze_backbone: bool = False,
        
        # Codebook config
        num_embeddings: int = 16384,
        embedding_dim: int = 1024,
        commitment_cost: float = 0.25,
        use_ema: bool = True,
        
        # Decoder config
        decoder_type: str = "cnn",
        decoder_channels: int = 256,
        
        # General
        patch_size: int = 16,
    ):
        super().__init__()
        
        self.patch_size = patch_size
        self.embedding_dim = embedding_dim
        self.num_embeddings = num_embeddings
        
        # Encoder
        if encoder_type == "vit":
            self.encoder = SemanticVQEncoder(
                backbone=backbone,
                embedding_dim=embedding_dim,
                patch_size=patch_size,
                freeze_backbone=freeze_backbone,
            )
        else:
            self.encoder = ConvSemanticEncoder(
                embedding_dim=embedding_dim,
            )
            
        # Codebook
        self.codebook = VQCodebook(
            num_embeddings=num_embeddings,
            embedding_dim=embedding_dim,
            commitment_cost=commitment_cost,
            use_ema=use_ema,
        )
        
        # Decoder
        if decoder_type == "cnn":
            self.decoder = SemanticVQDecoder(
                embedding_dim=embedding_dim,
                base_channels=decoder_channels,
            )
        else:
            self.decoder = TransformerVQDecoder(
                embedding_dim=embedding_dim,
            )
            
    def forward(
        self, 
        images: torch.Tensor,
        return_all: bool = False,
    ) -> Tuple[torch.Tensor, torch.Tensor, Dict[str, torch.Tensor]]:
        """
        Full forward pass: encode, quantize, decode.
        
        Args:
            images: [B, 3, H, W] input images (normalized to [-1, 1])
            return_all: Return intermediate outputs
            
        Returns:
            reconstructed: [B, 3, H, W] reconstructed images
            indices: [B, H//P, W//P] VQ token indices
            losses: Dict with all losses
        """
        # Encode
        z, enc_info = self.encoder(images)  # [B, H//P, W//P, D]
        
        # Quantize
        z_q, indices, vq_losses = self.codebook(z)
        
        # Decode
        reconstructed, dec_info = self.decoder(z_q)
        
        # Compute reconstruction loss
        recon_loss = F.mse_loss(reconstructed, images)
        
        # Combine losses
        losses = {
            "reconstruction": recon_loss,
            **vq_losses,
        }
        losses["total"] = recon_loss + vq_losses.get("commitment", 0)
        
        if return_all:
            losses["z"] = z
            losses["z_q"] = z_q
            losses["enc_info"] = enc_info
            losses["dec_info"] = dec_info
            
        return reconstructed, indices, losses
    
    def encode(
        self, 
        images: torch.Tensor,
        return_embeddings: bool = False,
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """
        Encode images to VQ indices only.
        
        Args:
            images: [B, 3, H, W]
            return_embeddings: Also return quantized embeddings
            
        Returns:
            indices: [B, H//P, W//P] token IDs
            z_q: Optional [B, H//P, W//P, D] embeddings
        """
        # Encode
        z, _ = self.encoder(images)
        
        # Quantize
        z_q, indices, _ = self.codebook(z)
        
        if return_embeddings:
            return indices, z_q
        return indices, None
    
    def decode(self, indices: torch.Tensor) -> torch.Tensor:
        """
        Decode from VQ indices.
        
        Args:
            indices: [B, H, W] token indices
            
        Returns:
            images: [B, 3, H*P, W*P]
        """
        # Get embeddings
        z_q = self.codebook.decode(indices)
        
        # Decode
        images, _ = self.decoder(z_q)
        
        return images
    
    def get_codebook_embeddings(self, indices: torch.Tensor) -> torch.Tensor:
        """
        Get embeddings for given indices (for DiT conditioning).
        
        Args:
            indices: [B, H, W] or [B, N] token indices
            
        Returns:
            embeddings: [B, H, W, D] or [B, N, D]
        """
        return self.codebook.decode(indices)
    
    def indices_to_sequence(
        self, 
        indices: torch.Tensor,
        offset: int = 135168,  # Offset после текстовых токенов
    ) -> torch.Tensor:
        """
        Convert spatial indices to sequence for AR model.
        
        Args:
            indices: [B, H, W] spatial indices
            offset: Token ID offset
            
        Returns:
            sequence: [B, H*W] token IDs with offset
        """
        B, H, W = indices.shape
        sequence = rearrange(indices, 'b h w -> b (h w)')
        return sequence + offset
    
    def sequence_to_indices(
        self,
        sequence: torch.Tensor,
        grid_size: Tuple[int, int],
        offset: int = 135168,
    ) -> torch.Tensor:
        """
        Convert sequence back to spatial indices.
        
        Args:
            sequence: [B, N] token IDs with offset
            grid_size: (H, W) target grid size
            offset: Token ID offset
            
        Returns:
            indices: [B, H, W] spatial indices
        """
        sequence = sequence - offset
        H, W = grid_size
        return rearrange(sequence, 'b (h w) -> b h w', h=H, w=W)

    @classmethod
    def from_config(cls, config: DictConfig) -> "SemanticVQModel":
        """Create model from config."""
        return cls(
            encoder_type=config.get("encoder_type", "vit"),
            backbone=config.encoder.get("backbone", "vit_large_patch16_384"),
            freeze_backbone=config.encoder.get("freeze_backbone", False),
            num_embeddings=config.codebook.num_embeddings,
            embedding_dim=config.codebook.embedding_dim,
            commitment_cost=config.codebook.commitment_cost,
            use_ema=config.codebook.use_ema,
            decoder_type=config.get("decoder_type", "cnn"),
            patch_size=config.encoder.patch_size,
        )


class VQTokenizer:
    """
    High-level tokenizer interface for VQ encoding.
    
    Handles:
    - Image preprocessing
    - Grid size calculation
    - Token offset management
    - Sequence formatting for AR model
    """
    
    def __init__(
        self,
        model: SemanticVQModel,
        token_offset: int = 135168,
        special_tokens: Optional[Dict[str, int]] = None,
    ):
        self.model = model
        self.token_offset = token_offset
        
        # Special tokens
        self.special_tokens = special_tokens or {
            "image_start": 135000,
            "image_end": 135001,
            "row_sep": 135002,
        }
        
        self.model.eval()
        
    @torch.no_grad()
    def encode(
        self,
        images: torch.Tensor,
        add_special_tokens: bool = True,
        include_row_sep: bool = False,
    ) -> Dict[str, torch.Tensor]:
        """
        Encode images to token sequences.
        
        Args:
            images: [B, 3, H, W] normalized images
            add_special_tokens: Add <image_start> and <image_end>
            include_row_sep: Add row separator tokens
            
        Returns:
            Dict with:
                - "input_ids": [B, N] token sequence
                - "grid_size": (H, W)
                - "attention_mask": [B, N]
        """
        # Encode to indices
        indices, _ = self.model.encode(images)
        B, H, W = indices.shape
        
        # Convert to sequence
        if include_row_sep:
            # Add row separators
            sequences = []
            for b in range(B):
                seq = []
                if add_special_tokens:
                    seq.append(self.special_tokens["image_start"])
                    
                for row in range(H):
                    row_tokens = indices[b, row, :] + self.token_offset
                    seq.extend(row_tokens.tolist())
                    if row < H - 1:
                        seq.append(self.special_tokens["row_sep"])
                        
                if add_special_tokens:
                    seq.append(self.special_tokens["image_end"])
                    
                sequences.append(torch.tensor(seq, device=indices.device))
                
            # Pad sequences
            max_len = max(len(s) for s in sequences)
            input_ids = torch.zeros(B, max_len, dtype=torch.long, device=indices.device)
            attention_mask = torch.zeros(B, max_len, dtype=torch.long, device=indices.device)
            
            for i, seq in enumerate(sequences):
                input_ids[i, :len(seq)] = seq
                attention_mask[i, :len(seq)] = 1
        else:
            # Simple flatten
            input_ids = self.model.indices_to_sequence(indices, self.token_offset)
            
            if add_special_tokens:
                start = torch.full((B, 1), self.special_tokens["image_start"], 
                                   device=indices.device, dtype=torch.long)
                end = torch.full((B, 1), self.special_tokens["image_end"],
                                 device=indices.device, dtype=torch.long)
                input_ids = torch.cat([start, input_ids, end], dim=1)
                
            attention_mask = torch.ones_like(input_ids)
            
        return {
            "input_ids": input_ids,
            "grid_size": (H, W),
            "attention_mask": attention_mask,
        }
    
    @torch.no_grad()
    def decode(
        self,
        input_ids: torch.Tensor,
        grid_size: Tuple[int, int],
        has_special_tokens: bool = True,
    ) -> torch.Tensor:
        """
        Decode token sequence to images.
        
        Args:
            input_ids: [B, N] token sequence
            grid_size: (H, W) target grid
            has_special_tokens: Remove special tokens first
            
        Returns:
            images: [B, 3, H*P, W*P]
        """
        H, W = grid_size
        
        if has_special_tokens:
            # Remove special tokens (first and last)
            input_ids = input_ids[:, 1:-1]
            
        # Remove row separators if present
        # Filter out special token IDs
        mask = (input_ids >= self.token_offset) & (
            input_ids < self.token_offset + self.model.num_embeddings
        )
        
        # Reshape to grid
        indices = self.model.sequence_to_indices(
            input_ids[:, :H*W],  # Take only grid tokens
            grid_size,
            self.token_offset,
        )
        
        # Decode
        return self.model.decode(indices)
    
    def get_vocab_size(self) -> int:
        """Total vocabulary size including special tokens."""
        return self.token_offset + self.model.num_embeddings + 10  # +10 for special
    
    def get_grid_size(self, resolution: Tuple[int, int]) -> Tuple[int, int]:
        """Calculate grid size for given resolution."""
        H, W = resolution
        patch_size = self.model.patch_size
        return H // patch_size, W // patch_size
    
    def get_num_tokens(self, resolution: Tuple[int, int]) -> int:
        """Calculate number of VQ tokens for given resolution."""
        H, W = self.get_grid_size(resolution)
        return H * W
