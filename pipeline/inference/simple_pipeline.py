"""
Simple Working Pipeline

Упрощённый рабочий пайплайн на базе open-source компонентов:
- VQ: VQGAN из taming-transformers
- AR: GPT-2 (дообученный на VQ токенах) или LLaMA
- Diffusion: Stable Diffusion VAE + UNet

Это демонстрационная версия, показывающая архитектуру.
Для production нужны обученные веса GLM-Image.
"""

import torch
import torch.nn as nn
from PIL import Image
from typing import Optional, Tuple, Dict, Any, List, Union
import numpy as np
from pathlib import Path


class SimpleImagePipeline:
    """
    Упрощённый рабочий пайплайн для генерации изображений.
    
    Использует доступные open-source модели:
    - Stable Diffusion для генерации
    - CLIP для text encoding
    - VQGAN для токенизации (опционально)
    
    Это не полная реализация GLM-Image, а рабочий демо-пайплайн.
    """
    
    def __init__(
        self,
        model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        enable_vq: bool = False,  # Опционально - VQ токенизация
        quantize: str = None,  # "4bit" или "8bit"
    ):
        """
        Args:
            model_id: HuggingFace model ID
            device: cuda/cpu
            dtype: torch.float16/float32
            enable_vq: Enable VQ tokenization (requires additional setup)
            quantize: "4bit" or "8bit" for reduced VRAM usage
        """
        self.device = device
        self.dtype = dtype
        self.model_id = model_id
        self.enable_vq = enable_vq
        self.quantize = quantize
        
        self._pipe = None
        self._i2i_pipe = None
        self._vq_model = None
        self._loaded = False
        
    def load(self):
        """Load models."""
        if self._loaded:
            return
            
        print(f"Loading {self.model_id}...")
        if self.quantize:
            print(f"Using {self.quantize} quantization")
        
        try:
            from diffusers import StableDiffusionXLPipeline, AutoencoderKL
            try:
                from transformers import BitsAndBytesConfig
            except ImportError:
                BitsAndBytesConfig = None
            
            # Quantization config
            load_kwargs = {
                "torch_dtype": self.dtype,
                "use_safetensors": True,
            }
            
            if self.quantize == "4bit":
                if BitsAndBytesConfig is None:
                    print("bitsandbytes/transformers BitsAndBytesConfig unavailable; falling back to fp16")
                else:
                    try:
                        quantization_config = BitsAndBytesConfig(
                            load_in_4bit=True,
                            bnb_4bit_compute_dtype=self.dtype,
                            bnb_4bit_quant_type="nf4",
                        )
                        load_kwargs["quantization_config"] = quantization_config
                        print("4-bit quantization enabled (saves ~75% VRAM)")
                    except Exception as e:
                        print(f"4-bit quantization failed ({e}); falling back to fp16")
                    
            elif self.quantize == "8bit":
                if BitsAndBytesConfig is None:
                    print("bitsandbytes/transformers BitsAndBytesConfig unavailable; falling back to fp16")
                else:
                    try:
                        quantization_config = BitsAndBytesConfig(load_in_8bit=True)
                        load_kwargs["quantization_config"] = quantization_config
                        print("8-bit quantization enabled (saves ~50% VRAM)")
                    except Exception as e:
                        print(f"8-bit quantization failed ({e}); falling back to fp16")
            else:
                load_kwargs["variant"] = "fp16" if self.dtype == torch.float16 else None

            pipe_kwargs = dict(load_kwargs)
            if self.dtype == torch.float16 and not self.quantize:
                try:
                    vae = AutoencoderKL.from_pretrained(
                        "madebyollin/sdxl-vae-fp16-fix",
                        torch_dtype=self.dtype,
                    )
                    pipe_kwargs["vae"] = vae
                    print("Using fp16-safe VAE (madebyollin/sdxl-vae-fp16-fix)")
                except Exception as e:
                    print(f"Could not load fp16 VAE, falling back to default: {e}")

            self._pipe = StableDiffusionXLPipeline.from_pretrained(
                self.model_id,
                **pipe_kwargs,
            )
            
            if not self.quantize:
                self._pipe.to(self.device)
            
            if hasattr(self._pipe, "enable_xformers_memory_efficient_attention"):
                try:
                    self._pipe.enable_xformers_memory_efficient_attention()
                except Exception:
                    pass
                    
            if self.quantize:
                try:
                    self._pipe.enable_model_cpu_offload()
                    print("CPU offload enabled")
                except Exception:
                    pass
                    
            print("Model loaded successfully!")
            
        except ImportError:
            print("diffusers not installed. Run: pip install diffusers transformers accelerate")
            raise
            
        if self.enable_vq:
            self._load_vq_model()
            
        self._loaded = True
        
    def _load_vq_model(self):
        """Load VQGAN for tokenization."""
        try:
            # Try to load from taming-transformers
            print("Loading VQGAN...")
            # Note: This requires taming-transformers to be installed
            # For simplicity, we'll use a basic VQ implementation
            pass
        except Exception as e:
            print(f"VQ model not loaded: {e}")
            self.enable_vq = False
            
    @torch.no_grad()
    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
        num_images: int = 1,
    ) -> List[Image.Image]:
        """
        Generate images from text prompt.
        
        Args:
            prompt: Text description. Put text to render in quotes: 'text "Hello World"'
            negative_prompt: Negative prompt
            width: Image width (multiple of 32)
            height: Image height (multiple of 32)
            num_inference_steps: Diffusion steps
            guidance_scale: CFG scale
            seed: Random seed
            num_images: Number of images to generate
            
        Returns:
            List of PIL Images
        """
        self.load()
        
        # Ensure dimensions are multiple of 32
        width = (width // 32) * 32
        height = (height // 32) * 32
        
        # Set seed
        generator = None
        if seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(seed)
            
        # Generate
        result = self._pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
            num_images_per_prompt=num_images,
        )
        
        return result.images
    
    @torch.no_grad()
    def image_to_image(
        self,
        image: Image.Image,
        prompt: str,
        negative_prompt: str = "",
        strength: float = 0.7,
        num_inference_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: Optional[int] = None,
        num_images: int = 1,
    ) -> List[Image.Image]:
        """Image-to-image via SDXL Img2Img."""
        self.load()
        from diffusers import StableDiffusionXLImg2ImgPipeline

        if not hasattr(self, "_i2i_pipe") or self._i2i_pipe is None:
            self._i2i_pipe = StableDiffusionXLImg2ImgPipeline(**self._pipe.components)
            if not self.quantize:
                self._i2i_pipe.to(self.device)

        generator = None
        if seed is not None:
            generator = torch.Generator(device=self.device).manual_seed(seed)

        result = self._i2i_pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            image=image.convert("RGB"),
            strength=strength,
            num_inference_steps=num_inference_steps,
            guidance_scale=guidance_scale,
            generator=generator,
            num_images_per_prompt=num_images,
        )
        return result.images

    @torch.no_grad()
    def encode_to_vq(self, image: Image.Image) -> torch.Tensor:
        """
        Encode image to VQ tokens (if VQ enabled).
        
        Args:
            image: PIL Image
            
        Returns:
            [H, W] tensor of VQ token indices
        """
        if not self.enable_vq or self._vq_model is None:
            raise RuntimeError("VQ model not loaded. Set enable_vq=True")
            
        # This would use the VQ encoder
        # For now, placeholder
        raise NotImplementedError("VQ encoding requires trained VQGAN model")
        
    @torch.no_grad() 
    def decode_from_vq(self, tokens: torch.Tensor) -> Image.Image:
        """
        Decode VQ tokens to image.
        
        Args:
            tokens: [H, W] VQ token indices
            
        Returns:
            PIL Image
        """
        if not self.enable_vq or self._vq_model is None:
            raise RuntimeError("VQ model not loaded")
            
        raise NotImplementedError("VQ decoding requires trained VQGAN model")
    
    def __call__(
        self,
        prompt: str,
        **kwargs,
    ) -> List[Image.Image]:
        """Shortcut for generate()."""
        return self.generate(prompt, **kwargs)


class TextRenderingPipeline(SimpleImagePipeline):
    """
    Pipeline optimized for text rendering.
    
    Обёртка над SimpleImagePipeline с дополнительной обработкой
    для лучшего рендеринга текста.
    """
    
    def __init__(self, **kwargs):
        # Use SDXL which is better at text
        kwargs.setdefault("model_id", "stabilityai/stable-diffusion-xl-base-1.0")
        super().__init__(**kwargs)
        
    def generate_with_text(
        self,
        description: str,
        text_to_render: str,
        style: str = "poster",
        **kwargs,
    ) -> List[Image.Image]:
        """
        Generate image with specific text.
        
        Args:
            description: Image description
            text_to_render: Exact text to render on image
            style: Style preset (poster, banner, sign, etc.)
            
        Returns:
            List of PIL Images
        """
        # Format prompt for text rendering
        # GLM-Image convention: text in quotes
        prompt = self._format_text_prompt(description, text_to_render, style)
        
        # Use higher guidance for text accuracy
        kwargs.setdefault("guidance_scale", 9.0)
        kwargs.setdefault("num_inference_steps", 50)
        
        return self.generate(prompt, **kwargs)
    
    def _format_text_prompt(
        self,
        description: str,
        text: str,
        style: str,
    ) -> str:
        """Format prompt for text rendering."""
        style_prompts = {
            "poster": "professional poster design, high quality typography",
            "banner": "advertising banner, bold text, eye-catching",
            "sign": "neon sign, glowing text, dark background",
            "logo": "minimalist logo design, clean typography",
            "meme": "meme format, impact font, white text with black outline",
        }
        
        style_desc = style_prompts.get(style, style)
        
        # GLM-Image format: text in quotes
        prompt = f'{description}, {style_desc}, text says "{text}", clear readable text, sharp typography'
        
        return prompt
    
    def validate_text(
        self,
        image: Image.Image,
        expected_text: str,
    ) -> Dict[str, Any]:
        """
        Validate rendered text using OCR.
        
        Args:
            image: Generated image
            expected_text: Expected text
            
        Returns:
            Dict with OCR results and accuracy metrics
        """
        try:
            from models.glyph_encoder import GlyphEncoder, TextAccuracyMetrics
            
            encoder = GlyphEncoder(device=self.device)
            result = encoder.recognize(image)
            
            metrics = TextAccuracyMetrics()
            accuracy = metrics.compute_all(expected_text, result["text"])
            
            return {
                "recognized_text": result["text"],
                "expected_text": expected_text,
                **accuracy,
            }
        except ImportError:
            return {"error": "OCR modules not available"}


def create_pipeline(
    pipeline_type: str = "simple",
    **kwargs,
) -> Union[SimpleImagePipeline, TextRenderingPipeline]:
    """
    Factory function to create pipelines.
    
    Args:
        pipeline_type: "simple" or "text_rendering"
        **kwargs: Pipeline arguments
        
    Returns:
        Pipeline instance
    """
    if pipeline_type == "simple":
        return SimpleImagePipeline(**kwargs)
    elif pipeline_type == "text_rendering":
        return TextRenderingPipeline(**kwargs)
    else:
        raise ValueError(f"Unknown pipeline type: {pipeline_type}")
