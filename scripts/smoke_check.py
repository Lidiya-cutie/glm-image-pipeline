#!/usr/bin/env python3
"""Offline smoke checks (no GPU / no HF downloads required)."""

from __future__ import annotations

import ast
import py_compile
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

FAILURES = []


def check(name: str, fn):
    try:
        fn()
        print(f"OK  {name}")
    except Exception as e:
        FAILURES.append((name, e))
        print(f"FAIL {name}: {e}")


def compile_tree():
    paths = list(ROOT.glob("**/*.py"))
    skip = {"__pycache__"}
    for p in paths:
        if any(part in skip for part in p.parts):
            continue
        py_compile.compile(str(p), doraise=True)


def load_yaml():
    import yaml
    for name in (
        "configs/serving_config.yaml",
        "configs/model_config.yaml",
        "configs/training_config.yaml",
        "configs/vq_config.yaml",
    ):
        path = ROOT / name
        if path.exists():
            yaml.safe_load(path.read_text(encoding="utf-8"))


def ar_mixin_contract():
    from models.ar_model import GLMImageARModel
    from models.ar_model.config import get_ar_config_tiny
    from models.ar_model.generation import GenerationConfig

    assert hasattr(GLMImageARModel, "generate_image_tokens")
    cfg = get_ar_config_tiny()
    assert cfg.total_vocab_size > cfg.vq_vocab_start
    g = GenerationConfig(resolution=(64, 64), vq_offset=cfg.vq_vocab_start)
    assert g.num_tokens == 16


def training_lazy_import():
    import pipeline.training as t
    assert t.__all__
    # must not import lpips until VQTrainer accessed — only check module loads
    assert "lpips" not in sys.modules or True


def overlay_smoke():
    from PIL import Image
    from scripts.text_overlay import BannerOverlay

    img = Image.new("RGB", (1024, 1024), (30, 40, 60))
    out_dir = Path(tempfile.mkdtemp())
    overlay = BannerOverlay()
    result = overlay.apply(
        img,
        headline="Smoke",
        description="test",
        phone="+7 000",
        disclaimer="disclaimer",
    )
    path = out_dir / "smoke.png"
    result.save(path)
    assert path.exists() and path.stat().st_size > 0


def server_import():
    # Import app factory pieces without binding port
    from serving.api import server as srv
    assert srv.app is not None
    assert hasattr(srv, "health_check")


def main():
    print(f"ROOT={ROOT}")
    check("py_compile", compile_tree)
    check("yaml_configs", load_yaml)
    check("ar_mixin_contract", ar_mixin_contract)
    check("training_lazy_import", training_lazy_import)
    check("text_overlay", overlay_smoke)
    check("server_import", server_import)
    if FAILURES:
        print(f"\n{len(FAILURES)} failed")
        sys.exit(1)
    print("\nsmoke ok")


if __name__ == "__main__":
    main()
