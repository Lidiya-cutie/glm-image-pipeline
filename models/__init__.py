"""
GLM-Image Models — lazy exports to avoid heavy optional deps at import time.
"""

__all__ = [
    "SemanticVQEncoder",
    "SemanticVQDecoder",
    "VQCodebook",
    "SemanticVQModel",
    "GLMImageARModel",
    "DiTDecoder",
    "GlyphEncoder",
]


def __getattr__(name: str):
    if name in ("SemanticVQEncoder", "SemanticVQDecoder", "VQCodebook", "SemanticVQModel"):
        from .vq_encoder import SemanticVQEncoder, SemanticVQDecoder, VQCodebook, SemanticVQModel
        mapping = {
            "SemanticVQEncoder": SemanticVQEncoder,
            "SemanticVQDecoder": SemanticVQDecoder,
            "VQCodebook": VQCodebook,
            "SemanticVQModel": SemanticVQModel,
        }
        return mapping[name]
    if name == "GLMImageARModel":
        from .ar_model import GLMImageARModel
        return GLMImageARModel
    if name == "DiTDecoder":
        from .dit_decoder import DiTDecoder
        return DiTDecoder
    if name == "GlyphEncoder":
        from .glyph_encoder import GlyphEncoder
        return GlyphEncoder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
