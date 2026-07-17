"""
Full GLM-Image Pipeline

Полный пайплайн GLM-Image:
1. Text → AR Model → VQ Tokens
2. VQ Tokens + Text → DiT → Latent
3. Latent → VAE Decoder → Image

Требует обученных весов для AR и DiT моделей.
"""

import torch
import torch.nn as nn
from PIL import Image
from typing import Optional, Tuple, Dict, Any, List, Union
import numpy as np
from pathlib import Path
from dataclasses import dataclass


@dataclass
class GenerationOutput:
    """Output from generation pipeline."""
    images: List[Image.Image]
    vq_tokens: Optional[torch.Tensor] = None
    latents: Optional[torch.Tensor] = None
    text_embeddings: Optional[torch.Tensor] = None
    metadata: Optional[Dict[str, Any]] = None


class GLMImagePipeline:
    """
    Full GLM-Image Pipeline.
    
    Architecture:
        Text Prompt 
            ↓
        [GLM Tokenizer] → text tokens
            ↓
        [AR Model 9B] → VQ semantic tokens
            ↓
        [VQ Codebook] → VQ embeddings
            ↓
        [DiT Decoder 7B] + text embeddings → latents
            ↓
        [VAE Decoder] → image
    
    Requires:
        - Trained AR model weights
        - Trained DiT model weights  
        - VQ codebook
        - VAE (can use SD VAE)
    """
    
    def __init__(
        self,
        ar_model_path: Optional[str] = None,
        dit_model_path: Optional[str] = None,
        vq_model_path: Optional[str] = None,
        vae_model_path: str = "stabilityai/sd-vae-ft-mse",
        device: str = "cuda",
        dtype: torch.dtype = torch.bfloat16,
    ):
        """
        Args:
            ar_model_path: Path to AR model checkpoint
            dit_model_path: Path to DiT model checkpoint
            vq_model_path: Path to VQ encoder checkpoint
            vae_model_path: VAE model (HF model ID or path)
            device: Device to use
            dtype: Model dtype
        """
        self.device = device
        self.dtype = dtype
        self.ar_model_path = ar_model_path
        self.dit_model_path = dit_model_path
        self.vq_model_path = vq_model_path
        self.vae_model_path = vae_model_path
        
        # Models (loaded lazily)
        self.ar_model = None
        self.dit_model = None
        self.vq_model = None
        self.vae = None
        self.tokenizer = None
        
        self._loaded = False
        
    def load(self):
        """Load all models."""
        if self._loaded:
            return
            
        print("Loading GLM-Image pipeline...")
        
        # Load VAE (always available from HF)
        self._load_vae()
        
        # Load VQ model
        if self.vq_model_path:
            self._load_vq_model()
        else:
            print("Warning: VQ model path not provided. Using mock VQ.")
            self._create_mock_vq()
            
        # Load AR model
        if self.ar_model_path:
            self._load_ar_model()
        else:
            print("Warning: AR model path not provided. Using mock AR.")
            self._create_mock_ar()
            
        # Load DiT model
        if self.dit_model_path:
            self._load_dit_model()
        else:
            print("Warning: DiT model path not provided. Using mock DiT.")
            self._create_mock_dit()
            
        # Load tokenizer
        self._load_tokenizer()
        
        self._loaded = True
        print("Pipeline loaded!")
        
    def _load_vae(self):
        """Load VAE decoder."""
        from diffusers import AutoencoderKL
        
        print(f"Loading VAE from {self.vae_model_path}...")
        self.vae = AutoencoderKL.from_pretrained(
            self.vae_model_path,
            torch_dtype=self.dtype,
        ).to(self.device)
        self.vae.eval()
        
    def _load_vq_model(self):
        """Load VQ encoder/decoder."""
        from models.vq_encoder import SemanticVQModel
        
        print(f"Loading VQ model from {self.vq_model_path}...")
        checkpoint = torch.load(self.vq_model_path, map_location="cpu")
        
        # Load config and model
        config = checkpoint.get("config", {})
        self.vq_model = SemanticVQModel(**config)
        self.vq_model.load_state_dict(checkpoint["model"])
        self.vq_model.to(self.device, dtype=self.dtype)
        self.vq_model.eval()
        
    def _create_mock_vq(self):
        """Create mock VQ for demo."""
        from models.vq_encoder import SemanticVQModel
        
        print("Creating mock VQ model (random weights)...")
        self.vq_model = SemanticVQModel(
            num_embeddings=16384,
            embedding_dim=1024,
        ).to(self.device, dtype=self.dtype)
        self.vq_model.eval()
        
    def _load_ar_model(self):
        """Load AR model."""
        from models.ar_model import GLMImageARModel, GLMImageARConfig
        
        print(f"Loading AR model from {self.ar_model_path}...")
        
        # Try loading from HF or local
        if Path(self.ar_model_path).exists():
            checkpoint = torch.load(self.ar_model_path, map_location="cpu")
            config = GLMImageARConfig(**checkpoint.get("config", {}))
            self.ar_model = GLMImageARModel(config)
            self.ar_model.load_state_dict(checkpoint["model"])
        else:
            # Try HuggingFace
            self.ar_model = GLMImageARModel.from_pretrained(self.ar_model_path)
            
        self.ar_model.to(self.device, dtype=self.dtype)
        self.ar_model.eval()
        
    def _create_mock_ar(self):
        """Create mock AR for demo (tiny — full 2B/9B without checkpoints OOMs)."""
        from models.ar_model import GLMImageARModel
        from models.ar_model.config import get_ar_config_tiny
        
        print("Creating mock AR model (tiny, random weights — not for quality)...")
        config = get_ar_config_tiny()
        self.ar_model = GLMImageARModel(config).to(self.device, dtype=self.dtype)
        self.ar_model.eval()
        
    def _load_dit_model(self):
        """Load DiT model."""
        from models.dit_decoder import DiTDecoder, DiTConfig
        
        print(f"Loading DiT model from {self.dit_model_path}...")
        checkpoint = torch.load(self.dit_model_path, map_location="cpu")
        
        config = DiTConfig(**checkpoint.get("config", {}))
        self.dit_model = DiTDecoder(config)
        self.dit_model.load_state_dict(checkpoint["model"])
        self.dit_model.to(self.device, dtype=self.dtype)
        self.dit_model.eval()
        
    def _create_mock_dit(self):
        """Create mock DiT for demo (tiny — full 3B/7B without checkpoints OOMs)."""
        from models.dit_decoder import DiTDecoder
        from models.dit_decoder.config import get_dit_config_tiny
        
        print("Creating mock DiT model (tiny, random weights — not for quality)...")
        config = get_dit_config_tiny()
        self.dit_model = DiTDecoder(config).to(self.device, dtype=self.dtype)
        self.dit_model.eval()
        
    def _load_tokenizer(self):
        """Load text tokenizer."""
        from transformers import AutoTokenizer
        
        try:
            # Try GLM-4 tokenizer
            self.tokenizer = AutoTokenizer.from_pretrained(
                "THUDM/glm-4-9b-chat",
                trust_remote_code=True,
            )
        except:
            # Fallback to GPT-2 tokenizer
            print("Using GPT-2 tokenizer as fallback")
            self.tokenizer = AutoTokenizer.from_pretrained("gpt2")
            self.tokenizer.pad_token = self.tokenizer.eos_token
            
    def _preprocess_prompt(self, prompt: str) -> str:
        """
        Preprocess prompt for GLM-Image.
        
        Text to render should be in quotes.
        """
        # Check if text is already quoted
        if '"' not in prompt:
            # Try to detect text to render and quote it
            # For now, just return as-is
            pass
        return prompt
    
    @torch.no_grad()
    def encode_prompt(
        self,
        prompt: str,
        max_length: int = 512,
    ) -> Dict[str, torch.Tensor]:
        """
        Encode text prompt to tokens.
        
        Returns:
            Dict with input_ids, attention_mask
        """
        prompt = self._preprocess_prompt(prompt)
        
        encoded = self.tokenizer(
            prompt,
            max_length=max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )
        
        return {
            "input_ids": encoded["input_ids"].to(self.device),
            "attention_mask": encoded["attention_mask"].to(self.device),
        }
    
    @torch.no_grad()
    def generate_vq_tokens(
        self,
        prompt_encoding: Dict[str, torch.Tensor],
        resolution: Tuple[int, int] = (1024, 1024),
        temperature: float = 0.9,
        top_p: float = 0.95,
        top_k: int = 50,
    ) -> torch.Tensor:
        """
        Generate VQ tokens using AR model.
        
        Args:
            prompt_encoding: Encoded prompt
            resolution: Target resolution
            temperature: Sampling temperature
            top_p: Top-p sampling
            top_k: Top-k sampling
            
        Returns:
            [B, H, W] VQ token indices
        """
        from models.ar_model.generation import GenerationConfig
        
        ar_cfg = self.ar_model.config
        config = GenerationConfig(
            resolution=resolution,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            image_start_id=ar_cfg.image_start_id,
            image_end_id=ar_cfg.image_end_id,
            vq_offset=ar_cfg.vq_vocab_start,
        )
        
        result = self.ar_model.generate_image_tokens(
            text_input_ids=prompt_encoding["input_ids"],
            text_attention_mask=prompt_encoding["attention_mask"],
            generation_config=config,
        )
        return result["vq_tokens"]
    
    @torch.no_grad()
    def decode_vq_to_image(
        self,
        vq_tokens: torch.Tensor,
        prompt_encoding: Dict[str, torch.Tensor],
        num_inference_steps: int = 50,
        guidance_scale: float = 7.5,
    ) -> torch.Tensor:
        """
        Decode VQ tokens to image using DiT.
        
        Args:
            vq_tokens: [B, H, W] VQ indices
            prompt_encoding: Text encoding
            num_inference_steps: DiT sampling steps
            guidance_scale: CFG scale
            
        Returns:
            [B, 3, H, W] images (normalized 0-1)
        """
        B = vq_tokens.shape[0]
        
        # Get VQ embeddings
        vq_embeddings = self.vq_model.get_codebook_embeddings(vq_tokens)
        vq_embeddings = vq_embeddings.view(B, -1, vq_embeddings.shape[-1])
        
        # Get text embeddings from AR model's hidden states
        ar_output = self.ar_model(
            input_ids=prompt_encoding["input_ids"],
            attention_mask=prompt_encoding["attention_mask"],
            output_hidden_states=True,
        )
        text_embeddings = ar_output.hidden_states[-1]  # Last layer
        
        # Compute latent size from VQ grid
        # VQ grid is image_size / 16, latent is image_size / 8
        # So latent is 2x VQ grid
        vq_h, vq_w = vq_tokens.shape[1], vq_tokens.shape[2]
        latent_h, latent_w = vq_h * 2, vq_w * 2
        
        # Sample using DiT
        latents = self.dit_model.sample(
            vq_embeddings=vq_embeddings,
            text_embeddings=text_embeddings,
            latent_size=(latent_h, latent_w),
            num_steps=num_inference_steps,
            cfg_scale=guidance_scale,
        )
        
        # Decode latents to image using VAE
        latents = latents / self.vae.config.scaling_factor
        images = self.vae.decode(latents.to(self.vae.dtype)).sample
        
        # Normalize to [0, 1]
        images = (images / 2 + 0.5).clamp(0, 1)
        
        return images
    
    @torch.no_grad()
    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        resolution: Tuple[int, int] = (1024, 1024),
        num_inference_steps: int = 50,
        guidance_scale: float = 7.5,
        temperature: float = 0.9,
        top_p: float = 0.95,
        seed: Optional[int] = None,
        return_intermediates: bool = False,
    ) -> GenerationOutput:
        """
        Full generation pipeline.
        
        Args:
            prompt: Text description with text to render in quotes
            negative_prompt: Negative prompt (not used in current implementation)
            resolution: Output resolution (H, W), must be multiple of 32
            num_inference_steps: DiT sampling steps
            guidance_scale: CFG scale for DiT
            temperature: AR sampling temperature
            top_p: AR top-p sampling
            seed: Random seed
            return_intermediates: Return intermediate tensors
            
        Returns:
            GenerationOutput with images and optionally intermediates
        """
        self.load()
        
        # Validate resolution
        h, w = resolution
        assert h % 32 == 0 and w % 32 == 0, "Resolution must be multiple of 32"
        
        # Set seed
        if seed is not None:
            torch.manual_seed(seed)
            
        # Step 1: Encode prompt
        prompt_encoding = self.encode_prompt(prompt)
        
        # Step 2: Generate VQ tokens
        print("Generating semantic VQ tokens...")
        vq_tokens = self.generate_vq_tokens(
            prompt_encoding,
            resolution=resolution,
            temperature=temperature,
            top_p=top_p,
        )
        
        # Step 3: Decode to image
        print("Decoding to image...")
        images_tensor = self.decode_vq_to_image(
            vq_tokens,
            prompt_encoding,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
        )
        
        # Convert to PIL
        images = []
        for img in images_tensor:
            img_np = (img.permute(1, 2, 0).cpu().numpy() * 255).astype(np.uint8)
            images.append(Image.fromarray(img_np))
            
        output = GenerationOutput(images=images)
        
        if return_intermediates:
            output.vq_tokens = vq_tokens
            output.latents = images_tensor
            
        return output
    
    def __call__(self, prompt: str, **kwargs) -> GenerationOutput:
        """Shortcut for generate()."""
        return self.generate(prompt, **kwargs)
    
    @torch.no_grad()
    def image_to_image(
        self,
        image: Image.Image,
        prompt: str,
        strength: float = 0.7,
        **kwargs,
    ) -> GenerationOutput:
        """
        Image-to-image generation.
        
        Args:
            image: Source image
            prompt: Edit instruction
            strength: How much to modify (0-1)
            **kwargs: Other generation arguments
            
        Returns:
            GenerationOutput
        """
        self.load()
        
        # Encode source image to VQ tokens
        img_tensor = self._preprocess_image(image)
        source_vq_tokens, _ = self.vq_model.encode(img_tensor)
        
        # Generate with source as condition
        prompt_encoding = self.encode_prompt(prompt)
        
        # For I2I, we pass source tokens to AR model
        # The AR model generates new tokens conditioned on source
        # This is simplified - full implementation would modify AR generation
        
        return self.generate(prompt, **kwargs)
    
    def _preprocess_image(self, image: Image.Image) -> torch.Tensor:
        """Preprocess PIL image to tensor."""
        import torchvision.transforms as T
        
        transform = T.Compose([
            T.Resize((1024, 1024)),
            T.ToTensor(),
            T.Normalize([0.5], [0.5]),
        ])
        
        return transform(image).unsqueeze(0).to(self.device, dtype=self.dtype)
