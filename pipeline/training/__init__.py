"""
Training pipelines for GLM-Image components.

Imports are lazy so `import pipeline.training` does not require lpips/wandb/deepspeed.
"""

__all__ = [
    "VQTrainer",
    "ARTrainer",
    "DiTTrainer",
    "GRPOTrainer",
]


def __getattr__(name: str):
    if name == "VQTrainer":
        from .train_vq import VQTrainer
        return VQTrainer
    if name == "ARTrainer":
        from .train_ar import ARTrainer
        return ARTrainer
    if name == "DiTTrainer":
        from .train_dit import DiTTrainer
        return DiTTrainer
    if name == "GRPOTrainer":
        from .train_grpo import GRPOTrainer
        return GRPOTrainer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
