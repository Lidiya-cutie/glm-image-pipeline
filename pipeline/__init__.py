"""
GLM-Image Pipelines

Inference and training pipelines.
"""

from .inference.pipeline import GLMImagePipeline
from .inference.simple_pipeline import SimpleImagePipeline

__all__ = [
    "GLMImagePipeline",
    "SimpleImagePipeline",
]
