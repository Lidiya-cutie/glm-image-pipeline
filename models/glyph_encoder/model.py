"""
Glyph Encoder - OCR модуль для RL rewards.

Использует PaddleOCR и EasyOCR для распознавания текста на изображениях.
"""

import torch
import torch.nn as nn
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image
import numpy as np


class GlyphEncoder(nn.Module):
    """
    Glyph Encoder для OCR.
    
    Распознаёт текст на изображениях для:
    1. Вычисления reward в RL (точность текста)
    2. Валидации качества генерации
    """
    
    def __init__(
        self,
        use_paddle: bool = True,
        use_easyocr: bool = True,
        languages: List[str] = ["en", "ch_sim"],
        device: str = "cuda",
        min_confidence: float = 0.5,
    ):
        super().__init__()
        
        self.use_paddle = use_paddle
        self.use_easyocr = use_easyocr
        self.languages = languages
        self.device = device
        self.min_confidence = min_confidence
        
        self._paddle_ocr = None
        self._easyocr_reader = None
        
    def _init_paddle(self):
        """Lazy init PaddleOCR."""
        if self._paddle_ocr is None and self.use_paddle:
            try:
                from paddleocr import PaddleOCR
                self._paddle_ocr = PaddleOCR(
                    use_angle_cls=True,
                    lang="ch",  # Supports both Chinese and English
                    show_log=False,
                    use_gpu=self.device == "cuda",
                )
            except ImportError:
                print("PaddleOCR not installed. Run: pip install paddleocr paddlepaddle-gpu")
                self.use_paddle = False
                
    def _init_easyocr(self):
        """Lazy init EasyOCR."""
        if self._easyocr_reader is None and self.use_easyocr:
            try:
                import easyocr
                self._easyocr_reader = easyocr.Reader(
                    self.languages,
                    gpu=self.device == "cuda",
                )
            except ImportError:
                print("EasyOCR not installed. Run: pip install easyocr")
                self.use_easyocr = False
                
    def recognize(
        self,
        image: Image.Image,
        return_boxes: bool = False,
    ) -> Dict[str, Any]:
        """
        Распознать текст на изображении.
        
        Args:
            image: PIL Image
            return_boxes: Возвращать ли bounding boxes
            
        Returns:
            Dict with:
                - "text": Full recognized text
                - "words": List of (text, confidence) tuples
                - "boxes": List of bounding boxes (if return_boxes)
        """
        results = {
            "text": "",
            "words": [],
            "boxes": [] if return_boxes else None,
            "paddle_results": None,
            "easyocr_results": None,
        }
        
        # Convert to numpy
        img_np = np.array(image)
        
        # PaddleOCR
        if self.use_paddle:
            self._init_paddle()
            if self._paddle_ocr is not None:
                paddle_result = self._paddle_ocr.ocr(img_np, cls=True)
                if paddle_result and paddle_result[0]:
                    for line in paddle_result[0]:
                        box, (text, conf) = line
                        if conf >= self.min_confidence:
                            results["words"].append((text, conf))
                            if return_boxes:
                                results["boxes"].append(box)
                    results["paddle_results"] = paddle_result
                    
        # EasyOCR
        if self.use_easyocr:
            self._init_easyocr()
            if self._easyocr_reader is not None:
                easy_result = self._easyocr_reader.readtext(img_np)
                for box, text, conf in easy_result:
                    if conf >= self.min_confidence:
                        # Avoid duplicates from PaddleOCR
                        if not any(w[0] == text for w in results["words"]):
                            results["words"].append((text, conf))
                            if return_boxes:
                                results["boxes"].append(box)
                results["easyocr_results"] = easy_result
                
        # Combine text
        results["text"] = " ".join([w[0] for w in results["words"]])
        
        return results
    
    @torch.no_grad()
    def batch_recognize(
        self,
        images: List[Image.Image],
    ) -> List[Dict[str, Any]]:
        """Batch OCR recognition."""
        return [self.recognize(img) for img in images]
    
    def compute_text_reward(
        self,
        image: Image.Image,
        target_text: str,
    ) -> Dict[str, float]:
        """
        Compute text accuracy reward.
        
        Args:
            image: Generated image
            target_text: Expected text (from prompt)
            
        Returns:
            Dict with reward metrics
        """
        from .metrics import TextAccuracyMetrics
        
        # Recognize
        result = self.recognize(image)
        recognized = result["text"]
        
        # Compute metrics
        metrics = TextAccuracyMetrics()
        
        return {
            "word_accuracy": metrics.word_accuracy(target_text, recognized),
            "char_accuracy": metrics.char_accuracy(target_text, recognized),
            "ned": metrics.normalized_edit_distance(target_text, recognized),
            "recognized_text": recognized,
            "target_text": target_text,
        }
