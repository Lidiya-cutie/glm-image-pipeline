#!/usr/bin/env python3
"""
vLLM Backend for AR Model

Запуск AR модели через vLLM для высокопроизводительного инференса.

Архитектура сервисов:
┌─────────────────────────────────────────────────────────────────┐
│                      API Gateway (:8080)                         │
│                            │                                     │
│        ┌──────────────────┼──────────────────┐                  │
│        ▼                  ▼                  ▼                  │
│  ┌──────────┐      ┌──────────┐       ┌──────────┐             │
│  │ vLLM AR  │      │   DiT    │       │   VQ     │             │
│  │ (:8000)  │      │ (:8001)  │       │ (:8002)  │             │
│  └──────────┘      └──────────┘       └──────────┘             │
└─────────────────────────────────────────────────────────────────┘

Запуск:
    # Только AR сервер через vLLM
    python -m serving.vllm_backend.launcher --model checkpoints/ar-model --port 8000
    
    # Все сервисы через docker-compose
    docker-compose up
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
import asyncio
from typing import Optional, List, Dict, Any
import torch


class VLLMARServer:
    """
    vLLM server для AR модели.
    
    Обёртка над vLLM для:
    1. Оптимизированного inference AR модели
    2. Batched generation VQ токенов
    3. Continuous batching для высокой пропускной способности
    """
    
    def __init__(
        self,
        model_path: str,
        tensor_parallel_size: int = 1,
        max_model_len: int = 8192,
        gpu_memory_utilization: float = 0.9,
        dtype: str = "bfloat16",
    ):
        """
        Args:
            model_path: Path to AR model checkpoint
            tensor_parallel_size: Number of GPUs for tensor parallelism
            max_model_len: Maximum sequence length
            gpu_memory_utilization: Fraction of GPU memory to use
            dtype: Model dtype
        """
        self.model_path = model_path
        self.tensor_parallel_size = tensor_parallel_size
        self.max_model_len = max_model_len
        self.gpu_memory_utilization = gpu_memory_utilization
        self.dtype = dtype
        
        self._engine = None
        
    def load(self):
        """Load vLLM engine."""
        if self._engine is not None:
            return
            
        try:
            from vllm import LLM, SamplingParams
            
            print(f"Loading AR model via vLLM from {self.model_path}...")
            
            self._engine = LLM(
                model=self.model_path,
                tensor_parallel_size=self.tensor_parallel_size,
                max_model_len=self.max_model_len,
                gpu_memory_utilization=self.gpu_memory_utilization,
                dtype=self.dtype,
                trust_remote_code=True,
            )
            
            print("vLLM engine loaded!")
            
        except ImportError:
            print("vLLM not installed. Run: pip install vllm")
            raise
            
    def generate_vq_tokens(
        self,
        prompts: List[str],
        max_vq_tokens: int = 4096,
        temperature: float = 0.9,
        top_p: float = 0.95,
        top_k: int = 50,
    ) -> List[List[int]]:
        """
        Generate VQ tokens for batch of prompts.
        
        Args:
            prompts: List of text prompts
            max_vq_tokens: Maximum VQ tokens to generate
            temperature: Sampling temperature
            top_p: Top-p sampling
            top_k: Top-k sampling
            
        Returns:
            List of VQ token sequences
        """
        self.load()
        
        from vllm import SamplingParams
        
        # Configure sampling
        sampling_params = SamplingParams(
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            max_tokens=max_vq_tokens,
            stop_token_ids=[135001],  # IMAGE_END
        )
        
        # Format prompts with special tokens
        formatted_prompts = [
            self._format_prompt(p) for p in prompts
        ]
        
        # Generate
        outputs = self._engine.generate(formatted_prompts, sampling_params)
        
        # Extract VQ tokens
        results = []
        for output in outputs:
            tokens = output.outputs[0].token_ids
            # Filter to VQ range
            vq_tokens = [t - 135168 for t in tokens if 135168 <= t < 135168 + 16384]
            results.append(vq_tokens)
            
        return results
    
    def _format_prompt(self, prompt: str) -> str:
        """Format prompt for AR model."""
        # Add special tokens
        return f"<|image_start|>{prompt}"
        
    def start_server(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
    ):
        """Start vLLM OpenAI-compatible server."""
        import subprocess
        
        cmd = [
            "python", "-m", "vllm.entrypoints.openai.api_server",
            "--model", self.model_path,
            "--host", host,
            "--port", str(port),
            "--tensor-parallel-size", str(self.tensor_parallel_size),
            "--max-model-len", str(self.max_model_len),
            "--gpu-memory-utilization", str(self.gpu_memory_utilization),
            "--dtype", self.dtype,
            "--trust-remote-code",
        ]
        
        print(f"Starting vLLM server on {host}:{port}")
        subprocess.run(cmd)


class DiTServer:
    """
    Server for DiT decoder.
    
    Отдельный сервис для DiT, так как он не может использовать vLLM напрямую.
    """
    
    def __init__(
        self,
        model_path: str,
        vae_path: str = "stabilityai/sd-vae-ft-mse",
        device: str = "cuda",
        dtype: str = "bfloat16",
    ):
        self.model_path = model_path
        self.vae_path = vae_path
        self.device = device
        self.dtype = getattr(torch, dtype)
        
        self._dit = None
        self._vae = None
        
    def load(self):
        """Load DiT and VAE models."""
        if self._dit is not None:
            return
            
        from models.dit_decoder import DiTDecoder, DiTConfig
        from diffusers import AutoencoderKL
        
        # Load DiT
        print(f"Loading DiT from {self.model_path}...")
        checkpoint = torch.load(self.model_path, map_location="cpu")
        config = DiTConfig(**checkpoint.get("config", {}))
        self._dit = DiTDecoder(config)
        self._dit.load_state_dict(checkpoint["model"])
        self._dit.to(self.device, dtype=self.dtype)
        self._dit.eval()
        
        # Load VAE
        print(f"Loading VAE from {self.vae_path}...")
        self._vae = AutoencoderKL.from_pretrained(
            self.vae_path,
            torch_dtype=self.dtype,
        ).to(self.device)
        
    @torch.no_grad()
    def generate(
        self,
        vq_embeddings: torch.Tensor,
        text_embeddings: torch.Tensor,
        latent_size: tuple = (128, 128),
        num_steps: int = 50,
        cfg_scale: float = 7.5,
    ) -> torch.Tensor:
        """Generate images from VQ embeddings."""
        self.load()
        
        # Sample latents
        latents = self._dit.sample(
            vq_embeddings=vq_embeddings.to(self.device, dtype=self.dtype),
            text_embeddings=text_embeddings.to(self.device, dtype=self.dtype),
            latent_size=latent_size,
            num_steps=num_steps,
            cfg_scale=cfg_scale,
        )
        
        # Decode with VAE
        latents = latents / self._vae.config.scaling_factor
        images = self._vae.decode(latents).sample
        
        return (images / 2 + 0.5).clamp(0, 1)


class OrchestratorServer:
    """
    Orchestrator that coordinates AR and DiT servers.
    
    Управляет полным пайплайном:
    1. Получает запрос
    2. Отправляет в AR server для генерации VQ токенов
    3. Отправляет VQ токены в DiT server
    4. Возвращает изображение
    """
    
    def __init__(
        self,
        ar_server_url: str = "http://localhost:8000",
        dit_server_url: str = "http://localhost:8001",
        vq_server_url: str = "http://localhost:8002",
    ):
        self.ar_url = ar_server_url
        self.dit_url = dit_server_url
        self.vq_url = vq_server_url
        
    async def generate(
        self,
        prompt: str,
        resolution: tuple = (1024, 1024),
        **kwargs,
    ) -> bytes:
        """
        Full generation pipeline through microservices.
        """
        import httpx
        
        async with httpx.AsyncClient(timeout=120) as client:
            # Step 1: Generate VQ tokens via AR server
            ar_response = await client.post(
                f"{self.ar_url}/v1/completions",
                json={
                    "prompt": f"<|image_start|>{prompt}",
                    "max_tokens": 4096,
                    "temperature": kwargs.get("temperature", 0.9),
                }
            )
            vq_tokens = ar_response.json()["choices"][0]["tokens"]
            
            # Step 2: Get VQ embeddings
            vq_response = await client.post(
                f"{self.vq_url}/embed",
                json={"tokens": vq_tokens}
            )
            vq_embeddings = vq_response.json()["embeddings"]
            
            # Step 3: Generate image via DiT server
            dit_response = await client.post(
                f"{self.dit_url}/generate",
                json={
                    "vq_embeddings": vq_embeddings,
                    "resolution": resolution,
                    **kwargs,
                }
            )
            
            return dit_response.content


def launch_ar_server(
    model_path: str,
    host: str = "0.0.0.0",
    port: int = 8000,
    tensor_parallel: int = 1,
):
    """Launch AR server via vLLM."""
    server = VLLMARServer(
        model_path=model_path,
        tensor_parallel_size=tensor_parallel,
    )
    server.start_server(host=host, port=port)


def main():
    parser = argparse.ArgumentParser(description="vLLM Backend Launcher")
    
    parser.add_argument("--model", type=str, required=True,
                        help="Path to AR model")
    parser.add_argument("--host", type=str, default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--tensor-parallel", type=int, default=1,
                        help="Tensor parallel size (number of GPUs)")
    parser.add_argument("--max-model-len", type=int, default=8192)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.9)
    
    args = parser.parse_args()
    
    launch_ar_server(
        model_path=args.model,
        host=args.host,
        port=args.port,
        tensor_parallel=args.tensor_parallel,
    )


if __name__ == "__main__":
    main()
