#!/usr/bin/env python3
"""
Постобработка: круглая композиция на белом фоне с чёрной окантовкой.

Секторы «прорыва» (breakout): вне круга + кольца, в указанных угловых диапазонах
(от 12 часов по часовой стрелке, 0°…360°) показываются пиксели исходного кадра —
имитация выхода динамики/частиц за границу (как в референс-описании).
"""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple, Union

import numpy as np
from PIL import Image, ImageDraw

Number = Union[int, float]


def _angle_from_12_clockwise_cw_deg(dx: np.ndarray, dy: np.ndarray) -> np.ndarray:
    """
    Угол в градусах: 0° = 12 часов, рост по часовой стрелке (3ч = 90°, 6ч = 180°).
    Экран: y вниз, x вправо.
    """
    rad = np.arctan2(dx.astype(np.float64), -dy.astype(np.float64))
    deg = np.degrees(rad) % 360.0
    return deg.astype(np.float32)


def _in_any_sector(angle_deg: np.ndarray, sectors: Sequence[Tuple[float, float]]) -> np.ndarray:
    """Маска True, если angle попадает в один из секторов [a,b) с учётом wrap по 360."""
    if not sectors:
        return np.zeros(angle_deg.shape, dtype=bool)
    out = np.zeros(angle_deg.shape, dtype=bool)
    for a, b in sectors:
        a = float(a) % 360.0
        b = float(b) % 360.0
        if a <= b:
            out |= (angle_deg >= a) & (angle_deg < b)
        else:
            out |= (angle_deg >= a) | (angle_deg < b)
    return out


def _apply_circular_frame_inscribed(
    src: np.ndarray,
    *,
    w: int,
    h: int,
    r_content: float,
    r_outer: float,
    tw: int,
    ring_color: Tuple[int, int, int, int],
    background: Tuple[int, int, int, int],
    breakout_sectors_deg: Optional[Sequence[Tuple[Number, Number]]],
    breakout_apply_beyond_ring: bool,
) -> Image.Image:
    out = np.full((h, w, 4), background, dtype=np.uint8)
    cx, cy = w / 2.0, h / 2.0
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    X, Y = np.meshgrid(xs, ys)
    dx = X - cx
    dy = Y - cy
    dist = np.sqrt(dx * dx + dy * dy)
    ang = _angle_from_12_clockwise_cw_deg(dx, dy)

    inside = dist < r_content
    out[inside] = src[inside]

    ring = (dist >= r_content) & (dist < r_outer)
    out[ring] = np.array(ring_color, dtype=np.uint8)

    beyond = dist >= r_outer
    sectors = list(breakout_sectors_deg or ())
    if sectors and breakout_apply_beyond_ring:
        br = _in_any_sector(ang, sectors) & beyond
        out[br] = src[br]

    return Image.fromarray(out, "RGBA")


def _apply_circular_frame_cover(
    image: Image.Image,
    *,
    w: int,
    h: int,
    r_content: float,
    r_outer: float,
    tw: int,
    ring_color: Tuple[int, int, int, int],
    background: Tuple[int, int, int, int],
    breakout_sectors_deg: Optional[Sequence[Tuple[Number, Number]]],
    breakout_apply_beyond_ring: bool,
) -> Image.Image:
    """
    Круг заполняется центральным кропом: масштаб как max(D/w,D/h), квадрат D×D по центру,
    затем в круге берутся пиксели из этого квадрата (плотное «отсечение по окружности»).
    """
    src_full = np.array(image.convert("RGBA"), dtype=np.uint8)
    iw, ih = image.size
    D = max(2, int(math.ceil(2.0 * r_content)))
    scale = max(D / float(iw), D / float(ih))
    nw = max(D, int(round(iw * scale)))
    nh = max(D, int(round(ih * scale)))
    resized = image.resize((nw, nh), Image.LANCZOS).convert("RGBA")
    left = (nw - D) // 2
    top = (nh - D) // 2
    patch = np.array(resized.crop((left, top, left + D, top + D)), dtype=np.uint8)
    if patch.shape[0] != D or patch.shape[1] != D:
        patch_im = Image.fromarray(patch, "RGBA").resize((D, D), Image.LANCZOS)
        patch = np.array(patch_im, dtype=np.uint8)

    out = np.full((h, w, 4), background, dtype=np.uint8)
    cx, cy = w / 2.0, h / 2.0
    pc = (D - 1) / 2.0
    xs = np.arange(w, dtype=np.float32)
    ys = np.arange(h, dtype=np.float32)
    X, Y = np.meshgrid(xs, ys)
    dx = X - cx
    dy = Y - cy
    dist = np.sqrt(dx * dx + dy * dy)
    ang = _angle_from_12_clockwise_cw_deg(dx, dy)

    inside = dist < r_content
    px = np.clip(np.round(pc + dx).astype(np.int32), 0, D - 1)
    py = np.clip(np.round(pc + dy).astype(np.int32), 0, D - 1)
    out[inside] = patch[py[inside], px[inside]]

    ring = (dist >= r_content) & (dist < r_outer)
    out[ring] = np.array(ring_color, dtype=np.uint8)

    beyond = dist >= r_outer
    sectors = list(breakout_sectors_deg or ())
    if sectors and breakout_apply_beyond_ring:
        br = _in_any_sector(ang, sectors) & beyond
        out[br] = src_full[Y[br].astype(np.int32), X[br].astype(np.int32)]

    return Image.fromarray(out, "RGBA")


def apply_circular_frame(
    image: Image.Image,
    *,
    content_radius_ratio: float = 0.42,
    ring_width_px: Optional[int] = None,
    ring_color: Tuple[int, int, int, int] = (0, 0, 0, 255),
    background: Tuple[int, int, int, int] = (255, 255, 255, 255),
    breakout_sectors_deg: Optional[Sequence[Tuple[Number, Number]]] = None,
    breakout_apply_beyond_ring: bool = True,
    fill_mode: str = "inscribed",
) -> Image.Image:
    """
    Накладывает круглую маску с чёрным кольцом и белым полем.

    :param content_radius_ratio: радиус диска с картинкой / (min(w,h)/2), < 0.5.
    :param ring_width_px: толщина кольца; по умолчанию ~1% от min стороны.
    :param breakout_sectors_deg: список (start, end) в градусах [0,360), от 12ч по ч.с.;
        вне диска + кольца в этих секторах подставляются пиксели исходника.
    :param fill_mode: ``inscribed`` — круг как «окно» в исходный кадр (по умолчанию);
        ``cover`` — масштаб и центральный кроп под круг (плотное заполнение диска).
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    w, h = image.size
    src = np.array(image, dtype=np.uint8)

    m = min(w, h)
    half = m / 2.0
    r_content = float(content_radius_ratio) * half
    if ring_width_px is None:
        tw = max(3, int(m * 0.012))
    else:
        tw = max(1, int(ring_width_px))
    r_outer = r_content + tw

    mode = (fill_mode or "inscribed").strip().lower()
    if mode == "cover":
        return _apply_circular_frame_cover(
            image,
            w=w,
            h=h,
            r_content=r_content,
            r_outer=r_outer,
            tw=tw,
            ring_color=ring_color,
            background=background,
            breakout_sectors_deg=breakout_sectors_deg,
            breakout_apply_beyond_ring=breakout_apply_beyond_ring,
        )
    return _apply_circular_frame_inscribed(
        src,
        w=w,
        h=h,
        r_content=r_content,
        r_outer=r_outer,
        tw=tw,
        ring_color=ring_color,
        background=background,
        breakout_sectors_deg=breakout_sectors_deg,
        breakout_apply_beyond_ring=breakout_apply_beyond_ring,
    )


def _rgba_from_cfg(val: object, default: Tuple[int, int, int, int]) -> Tuple[int, int, int, int]:
    if isinstance(val, (list, tuple)) and len(val) >= 3:
        t = [int(x) for x in val[:4]]
        if len(t) == 3:
            t.append(255)
        return (t[0], t[1], t[2], t[3])
    return default


def apply_circular_frame_from_config(
    image: Image.Image,
    framing: Optional[dict],
) -> Image.Image:
    """Параметры из сценария: framing: { content_radius_ratio, ring_width_px, breakout_sectors }."""
    if not framing:
        return apply_circular_frame(image)
    sectors = framing.get("breakout_sectors") or []
    parsed: List[Tuple[float, float]] = []
    for item in sectors:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            parsed.append((float(item[0]), float(item[1])))
    return apply_circular_frame(
        image,
        content_radius_ratio=float(framing.get("content_radius_ratio", 0.42)),
        ring_width_px=framing.get("ring_width_px"),
        ring_color=_rgba_from_cfg(framing.get("ring_color"), (0, 0, 0, 255)),
        background=_rgba_from_cfg(framing.get("background"), (255, 255, 255, 255)),
        breakout_sectors_deg=parsed or None,
        breakout_apply_beyond_ring=bool(framing.get("breakout_apply_beyond_ring", True)),
        fill_mode=str(framing.get("fill_mode") or "inscribed"),
    )
