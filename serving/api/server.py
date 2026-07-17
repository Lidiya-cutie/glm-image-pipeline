#!/usr/bin/env python3
"""
GLM-Image API Server (Simple Mode = SDXL by default).

Запуск:
    python -m serving.api.server --port 8080

Endpoints:
    GET  /health, /ready
    POST /generate, /generate/text, /i2i
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import asyncio
import base64
import io
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional

import torch
import uvicorn
import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from pipeline.inference.simple_pipeline import SimpleImagePipeline, TextRenderingPipeline

CONFIG_PATH = Path(os.environ.get("GLM_SERVING_CONFIG", PROJECT_ROOT / "configs" / "serving_config.yaml"))
OUTPUT_DIR = Path(os.environ.get("GLM_OUTPUT_DIR", PROJECT_ROOT / "outputs" / "api"))


def load_serving_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


SERVING_CFG = load_serving_config()
API_CFG = SERVING_CFG.get("api_gateway", {})
RATE_CFG = API_CFG.get("rate_limit", {}) or {}
AUTH_CFG = API_CFG.get("auth", {}) or {}
CORS_CFG = API_CFG.get("cors", {}) or {}
REQUEST_CFG = API_CFG.get("request", {}) or {}

MAX_CONCURRENT = int(os.environ.get("GLM_MAX_CONCURRENT", API_CFG.get("max_concurrent", 1)))
RATE_ENABLED = bool(RATE_CFG.get("enabled", False))
RATE_RPM = int(RATE_CFG.get("requests_per_minute", 60))
AUTH_ENABLED = bool(AUTH_CFG.get("enabled", False))
API_KEYS = set(AUTH_CFG.get("api_keys") or [])
if os.environ.get("GLM_API_KEY"):
    API_KEYS.add(os.environ["GLM_API_KEY"])
    AUTH_ENABLED = True


class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="Text prompt. Put text to render in quotes.")
    negative_prompt: str = Field("", description="Negative prompt")
    width: int = Field(1024, ge=256, le=2048)
    height: int = Field(1024, ge=256, le=2048)
    num_inference_steps: int = Field(50, ge=1, le=100)
    guidance_scale: float = Field(7.5, ge=1.0, le=20.0)
    temperature: float = Field(0.9, ge=0.1, le=2.0)
    seed: Optional[int] = None
    num_images: int = Field(1, ge=1, le=4)
    output_format: str = Field("png")
    return_base64: bool = Field(True)


class TextRenderRequest(BaseModel):
    description: str
    text_to_render: str
    style: str = Field("poster")
    width: int = Field(1024, ge=256, le=2048)
    height: int = Field(1024, ge=256, le=2048)
    num_inference_steps: int = Field(50, ge=1, le=100)
    guidance_scale: float = Field(9.0, ge=1.0, le=20.0)
    seed: Optional[int] = None
    validate_text: bool = False


class I2IRequest(BaseModel):
    image_base64: str
    prompt: str
    strength: float = Field(0.7, ge=0.0, le=1.0)
    negative_prompt: str = ""
    num_inference_steps: int = Field(50, ge=1, le=100)
    guidance_scale: float = Field(7.5, ge=1.0, le=20.0)
    seed: Optional[int] = None
    return_base64: bool = True
    output_format: str = "png"


class GenerateResponse(BaseModel):
    images: List[str]
    seed: int
    metadata: dict = {}


class HealthResponse(BaseModel):
    status: str
    gpu_available: bool
    models_loaded: bool
    max_concurrent: int
    mode: str = "simple-sdxl"
    timestamp: str


app = FastAPI(
    title="GLM-Image API",
    description="Production-oriented API. Default backend is SDXL Simple Mode; full GLM needs checkpoints.",
    version="1.1.0",
)

cors_origins = CORS_CFG.get("allow_origins", ["*"]) if CORS_CFG.get("enabled", True) else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["*"],
    allow_credentials=False if cors_origins == ["*"] else True,
    allow_methods=CORS_CFG.get("allow_methods", ["GET", "POST"]),
    allow_headers=["*"],
)

_pipeline: Optional[SimpleImagePipeline] = None
_text_pipeline: Optional[TextRenderingPipeline] = None
_infer_lock = asyncio.Semaphore(MAX_CONCURRENT)
_rate_buckets: Dict[str, Deque[float]] = defaultdict(deque)
_started_at = datetime.now(timezone.utc).isoformat()


def _client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    if not RATE_ENABLED:
        return
    now = time.time()
    window = 60.0
    bucket = _rate_buckets[_client_id(request)]
    while bucket and now - bucket[0] > window:
        bucket.popleft()
    if len(bucket) >= RATE_RPM:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if not AUTH_ENABLED:
        return
    if not x_api_key or x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


def get_pipeline() -> SimpleImagePipeline:
    global _pipeline
    if _pipeline is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        _pipeline = SimpleImagePipeline(device=device, dtype=dtype)
        _pipeline.load()
    return _pipeline


def get_text_pipeline() -> TextRenderingPipeline:
    global _text_pipeline
    if _text_pipeline is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        _text_pipeline = TextRenderingPipeline(device=device, dtype=dtype)
        _text_pipeline.load()
    return _text_pipeline


def _encode_images(images, output_format: str, return_base64: bool) -> List[str]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    encoded: List[str] = []
    fmt = output_format.upper()
    for idx, img in enumerate(images):
        buffer = io.BytesIO()
        img.save(buffer, format=fmt)
        buffer.seek(0)
        if return_base64:
            b64 = base64.b64encode(buffer.read()).decode()
            encoded.append(f"data:image/{output_format.lower()};base64,{b64}")
        else:
            name = f"gen_{int(time.time() * 1000)}_{idx}.{output_format.lower()}"
            path = OUTPUT_DIR / name
            path.write_bytes(buffer.getvalue())
            encoded.append(str(path))
    return encoded


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        gpu_available=torch.cuda.is_available(),
        models_loaded=_pipeline is not None and getattr(_pipeline, "_loaded", False),
        max_concurrent=MAX_CONCURRENT,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/ready")
async def ready_check():
    """Readiness: process up. Model may load lazily on first generate."""
    return {
        "ready": True,
        "models_loaded": _pipeline is not None and getattr(_pipeline, "_loaded", False),
        "started_at": _started_at,
        "gpu_available": torch.cuda.is_available(),
    }


@app.post("/generate", response_model=GenerateResponse, dependencies=[Depends(require_api_key)])
async def generate(request: GenerateRequest, raw: Request):
    check_rate_limit(raw)
    max_res = REQUEST_CFG.get("max_resolution", [2048, 2048])
    if request.width > max_res[1] or request.height > max_res[0]:
        raise HTTPException(status_code=400, detail=f"Resolution exceeds max {max_res}")

    try:
        async with _infer_lock:
            pipeline = await asyncio.to_thread(get_pipeline)
            width = (request.width // 32) * 32
            height = (request.height // 32) * 32
            seed = request.seed if request.seed is not None else int(torch.randint(0, 2**31 - 1, (1,)).item())
            images = await asyncio.to_thread(
                pipeline.generate,
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                width=width,
                height=height,
                num_inference_steps=request.num_inference_steps,
                guidance_scale=request.guidance_scale,
                seed=seed,
                num_images=request.num_images,
            )
            encoded = await asyncio.to_thread(
                _encode_images, images, request.output_format, request.return_base64
            )
        return GenerateResponse(
            images=encoded,
            seed=seed,
            metadata={
                "width": width,
                "height": height,
                "steps": request.num_inference_steps,
                "cfg_scale": request.guidance_scale,
                "backend": "sdxl-simple",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/generate/text", response_model=GenerateResponse, dependencies=[Depends(require_api_key)])
async def generate_with_text(request: TextRenderRequest, raw: Request):
    check_rate_limit(raw)
    try:
        async with _infer_lock:
            pipeline = await asyncio.to_thread(get_text_pipeline)
            width = (request.width // 32) * 32
            height = (request.height // 32) * 32
            seed = request.seed if request.seed is not None else int(torch.randint(0, 2**31 - 1, (1,)).item())
            images = await asyncio.to_thread(
                pipeline.generate_with_text,
                description=request.description,
                text_to_render=request.text_to_render,
                style=request.style,
                width=width,
                height=height,
                num_inference_steps=request.num_inference_steps,
                guidance_scale=request.guidance_scale,
                seed=seed,
            )
            validation_result = None
            if request.validate_text:
                validation_result = await asyncio.to_thread(
                    pipeline.validate_text, images[0], request.text_to_render
                )
            encoded = await asyncio.to_thread(_encode_images, images, "png", True)
        return GenerateResponse(
            images=encoded,
            seed=seed,
            metadata={
                "width": width,
                "height": height,
                "text_to_render": request.text_to_render,
                "style": request.style,
                "validation": validation_result,
                "backend": "sdxl-simple",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/i2i", response_model=GenerateResponse, dependencies=[Depends(require_api_key)])
async def image_to_image(request: I2IRequest, raw: Request):
    check_rate_limit(raw)
    try:
        from PIL import Image

        image_data = base64.b64decode(request.image_base64.split(",")[-1])
        source_image = Image.open(io.BytesIO(image_data)).convert("RGB")
        async with _infer_lock:
            pipeline = await asyncio.to_thread(get_pipeline)
            seed = request.seed if request.seed is not None else int(torch.randint(0, 2**31 - 1, (1,)).item())
            images = await asyncio.to_thread(
                pipeline.image_to_image,
                image=source_image,
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                strength=request.strength,
                num_inference_steps=request.num_inference_steps,
                guidance_scale=request.guidance_scale,
                seed=seed,
            )
            encoded = await asyncio.to_thread(
                _encode_images, images, request.output_format, request.return_base64
            )
        return GenerateResponse(
            images=encoded,
            seed=seed,
            metadata={"strength": request.strength, "backend": "sdxl-img2img"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"detail": str(exc)})


def main():
    import argparse

    parser = argparse.ArgumentParser(description="GLM-Image API Server")
    parser.add_argument("--host", type=str, default=API_CFG.get("host", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(API_CFG.get("port", 8080)))
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    if args.workers > 1:
        print("Warning: workers>1 duplicates GPU models; prefer GLM_MAX_CONCURRENT=1 + single worker.")

    print(f"Starting API on {args.host}:{args.port} (max_concurrent={MAX_CONCURRENT})")
    print(f"Config: {CONFIG_PATH}")
    print(f"Docs: http://{args.host}:{args.port}/docs")

    uvicorn.run(
        "serving.api.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
