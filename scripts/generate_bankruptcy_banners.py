#!/usr/bin/env python3
"""
Full Bankruptcy Ad Banner Generator

Полный пайплайн генерации рекламных баннеров о банкротстве физлиц:
1. Генерация фонового изображения (SDXL)
2. Наложение текста с учётом законодательства РФ

КОНТЕНТ (расширенный):
📊 20 сценариев фонов (офисы, суды, документы, абстрактные)
📊 20 заголовков (все содержат "банкротство")
📊 20 описаний услуг (без обещаний списания)
📊 21 дисклеймер (по периодам: 2024, 2025, 2026)
📊 13 стилей фона дисклеймера (сплошные, градиентные, вытянутые)

СТРУКТУРИРОВАННЫЙ КОНТЕНТ (НОВОЕ!):
📋 10 маркированных списков с левой/правой позицией
📋 5 структурированных блоков (заголовок + подзаголовок + список + CTA)
📋 10 расширенных заголовков с подзаголовками
📋 8 кнопок CTA (призывы к действию)
📋 5 информационных блоков

ТРЕБОВАНИЯ ЗАКОНОДАТЕЛЬСТВА (38-ФЗ):
✅ ОБЯЗАТЕЛЬНО:
   - Слово "банкротство" или "банкротство физлиц"
   - С 01.09.2025: предупредительная надпись
   - С 01.01.2026: предупреждение о последствиях + льготные варианты

❌ ЗАПРЕЩЕНО:
   - "спишем долги", "списание долгов", "избавим от долгов"
   - "гарантированно", "100%", "навсегда"
   - Обещания освобождения от обязательств
   - Банкротство юрлиц (только физлица!)

Примеры:
    # === ПРОСТЫЕ БАННЕРЫ ===
    
    # Один баннер
    python scripts/generate_bankruptcy_banners.py --scenario office_professional

    # Все сценарии (20 штук)
    python scripts/generate_bankruptcy_banners.py --all-scenarios --output output/bankruptcy/

    # С квантизацией для экономии VRAM
    python scripts/generate_bankruptcy_banners.py --all-scenarios --quantize 4bit

    # === СТРУКТУРИРОВАННЫЕ БАННЕРЫ (НОВОЕ!) ===
    
    # Один структурированный баннер (с маркированным списком справа)
    python scripts/generate_bankruptcy_banners.py --structured \\
        --output output/bankruptcy_structured/

    # Баннер с маркированным списком (выбор позиции)
    python scripts/generate_bankruptcy_banners.py --bullet-list --list-position left \\
        --output output/bankruptcy_bullets/

    # Массовая генерация структурированных баннеров
    python scripts/generate_bankruptcy_banners.py --mass-structured 500 \\
        --banner-type mixed \\
        --output output/bankruptcy_structured_mass/

    # Только баннеры с маркированными списками
    python scripts/generate_bankruptcy_banners.py --mass-structured 200 \\
        --banner-type bullet \\
        --output output/bankruptcy_bullets_mass/

    # === МАССОВАЯ ГЕНЕРАЦИЯ 2000 БАННЕРОВ ===
    python scripts/generate_bankruptcy_banners.py --mass-generate 2000 \\
        --output output/bankruptcy_mass/ \\
        --quantize 4bit \\
        --steps 30 \\
        --save-metadata

    # Быстрая генерация 100 тестовых баннеров
    python scripts/generate_bankruptcy_banners.py --mass-generate 100 \\
        --output output/bankruptcy_test/ \\
        --quantize 8bit \\
        --steps 25

    # === УТИЛИТЫ ===
    
    # Проверить текст на законность
    python scripts/generate_bankruptcy_banners.py --validate "Спишем ваши долги"

    # Посмотреть статистику комбинаций
    python scripts/generate_bankruptcy_banners.py --show-stats

    # Список всех заголовков
    python scripts/generate_bankruptcy_banners.py --list-headlines

    # Список маркированных списков
    python scripts/generate_bankruptcy_banners.py --list-bullet-lists

    # Структурированный контент
    python scripts/generate_bankruptcy_banners.py --list-structured
"""

import argparse
import sys
from pathlib import Path
import json
import random
from typing import Dict, List, Optional, Any
import torch
from PIL import Image
from datetime import date

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.bankruptcy_overlay import (
    BankruptcyBannerOverlay,
    TextValidator,
    BANKRUPTCY_HEADLINES,
    BANKRUPTCY_DESCRIPTIONS,
    BANKRUPTCY_SCENARIOS,
    BANKRUPTCY_STYLES,
    BANKRUPTCY_DISCLAIMERS_2024,
    BANKRUPTCY_DISCLAIMERS_2025,
    BANKRUPTCY_DISCLAIMERS_2026,
    DISCLAIMER_BG_STYLES,
    get_appropriate_disclaimer,
    generate_phone,
    get_random_disclaimer_bg_style,
    get_disclaimer_bg_style_by_name,
    # Новые структурированные элементы
    BULLET_LISTS,
    EXTENDED_HEADLINES,
    CTA_BUTTONS,
    INFO_BLOCKS,
    STRUCTURED_CONTENT,
    get_random_bullet_list,
    get_random_extended_headline,
    get_random_structured_content,
    get_random_cta,
    get_random_info_block,
)
from scripts.text_overlay import LAYOUTS, get_layout_by_name
import time


# Негативные промпты
NEG_PROMPT = "text, words, letters, watermark, logo, cartoon, anime, 3d render, people, person, face, hands, cluttered, bright neon colors, low quality, blurry, deformed"


class BankruptcyBannerPipeline:
    """
    Полный пайплайн: генерация фона + наложение текста.
    С валидацией на соответствие законодательству.
    """
    
    def __init__(
        self,
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        quantize: str = None,
        validate: bool = True,
    ):
        self.device = device
        self.dtype = dtype
        self.quantize = quantize
        self.validate = validate
        self._pipeline = None
    
    def load(self):
        """Загрузка модели генерации."""
        if self._pipeline is not None:
            return
        
        from pipeline.inference.simple_pipeline import SimpleImagePipeline
        
        print("Загрузка модели...")
        self._pipeline = SimpleImagePipeline(
            device=self.device,
            dtype=self.dtype,
            quantize=self.quantize,
        )
        self._pipeline.load()
    
    def generate_background(
        self,
        scenario: Dict[str, Any],
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: int = None,
    ) -> Image.Image:
        """Генерация фонового изображения."""
        self.load()
        
        images = self._pipeline.generate(
            prompt=scenario["prompt"],
            negative_prompt=NEG_PROMPT,
            width=width,
            height=height,
            num_inference_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
            num_images=1,
        )
        
        return images[0]
    
    def generate_banner(
        self,
        scenario: Dict[str, Any] = None,
        headline: str = None,
        description: str = None,
        phone: str = None,
        disclaimer: str = None,
        layout: Dict = None,
        style: Dict = None,
        disclaimer_bg_style: Dict = None,
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: int = None,
    ) -> Image.Image:
        """
        Генерация полного баннера: фон + текст.
        
        Валидирует тексты на соответствие закону.
        """
        scenario = scenario or random.choice(BANKRUPTCY_SCENARIOS)
        layout = layout or random.choice(LAYOUTS)
        style = style or random.choice(BANKRUPTCY_STYLES)
        
        # Генерируем фон
        print(f"  Генерация фона: {scenario['name']}...")
        background = self.generate_background(
            scenario=scenario,
            width=width,
            height=height,
            num_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )
        
        # Накладываем текст
        disc_bg_name = disclaimer_bg_style['name'] if disclaimer_bg_style else "random"
        print(f"  Наложение текста (стиль: {style['name']}, дисклеймер: {disc_bg_name})...")
        overlay = BankruptcyBannerOverlay(
            layout=layout,
            style=style,
            disclaimer_bg_style=disclaimer_bg_style,
            validate=self.validate,
        )
        
        result = overlay.apply(
            background,
            headline=headline,
            description=description,
            phone=phone,
            disclaimer=disclaimer,
        )
        
        return result
    
    def generate_batch(
        self,
        scenarios: List[Dict],
        output_dir: Path,
        variations: int = 1,
        layout: Dict = None,
        style: Dict = None,
        disclaimer_bg_style: Dict = None,
        **kwargs,
    ) -> List[Dict]:
        """Генерация нескольких баннеров."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        count = 0
        
        for scenario in scenarios:
            for var in range(variations):
                count += 1
                print(f"\n[{count}] Сценарий: {scenario['name']} (вариация {var+1})")
                
                # Используем переданные или выбираем случайные
                use_layout = layout if layout else random.choice(LAYOUTS)
                use_style = style if style else random.choice(BANKRUPTCY_STYLES)
                use_disc_bg = disclaimer_bg_style if disclaimer_bg_style else get_random_disclaimer_bg_style()
                
                try:
                    image = self.generate_banner(
                        scenario=scenario,
                        layout=use_layout,
                        style=use_style,
                        disclaimer_bg_style=use_disc_bg,
                        **kwargs,
                    )
                    
                    filename = f"{scenario['name']}_{use_style['name']}_{use_disc_bg['name']}_{var:02d}.png"
                    filepath = output_dir / filename
                    image.save(filepath, quality=95)
                    
                    results.append({
                        "filename": str(filepath),
                        "scenario": scenario['name'],
                        "style": use_style['name'],
                        "disclaimer_bg": use_disc_bg['name'],
                    })
                    
                    print(f"  ✅ Сохранено: {filepath}")
                    
                except ValueError as e:
                    print(f"  ❌ Ошибка: {e}")
        
        return results
    
    def generate_mass_random(
        self,
        output_dir: Path,
        total_count: int = 2000,
        save_stats: bool = True,
        **kwargs,
    ) -> List[Dict]:
        """
        Массовая генерация случайных баннеров.
        
        Полностью случайная комбинация:
        - Сценарий фона
        - Стиль текста
        - Стиль фона дисклеймера
        - Заголовок
        - Описание
        - Дисклеймер
        - Лейаут
        
        Args:
            output_dir: Папка для сохранения
            total_count: Общее количество баннеров
            save_stats: Сохранять детальную статистику в CSV/JSON
            **kwargs: Дополнительные параметры (width, height, num_steps, etc.)
        
        Returns:
            Список метаданных созданных баннеров
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        errors = []
        timing_stats = []  # Статистика по времени каждого баннера
        start_time = time.time()
        
        print(f"\n{'='*70}")
        print(f"  МАССОВАЯ ГЕНЕРАЦИЯ БАННЕРОВ О БАНКРОТСТВЕ")
        print(f"  Дата: {date.today().isoformat()}")
        print(f"  Всего: {total_count} баннеров")
        print(f"  Папка: {output_dir}")
        print(f"  Параметры: {kwargs}")
        print(f"{'='*70}\n")
        
        for i in range(total_count):
            banner_start = time.time()
            
            # Полностью случайный выбор всех параметров
            scenario = random.choice(BANKRUPTCY_SCENARIOS)
            style = random.choice(BANKRUPTCY_STYLES)
            layout = random.choice(LAYOUTS)
            disc_bg = get_random_disclaimer_bg_style()
            headline = random.choice(BANKRUPTCY_HEADLINES)
            description = random.choice(BANKRUPTCY_DESCRIPTIONS)
            disclaimer = get_appropriate_disclaimer()
            phone = generate_phone()
            
            # Уникальный seed для каждого изображения
            seed = random.randint(1, 999999999)
            
            progress = (i + 1) / total_count * 100
            elapsed = time.time() - start_time
            avg_time = elapsed / (i + 1) if i > 0 else 30
            eta = avg_time * (total_count - i - 1)
            
            print(f"\n[{i+1}/{total_count}] ({progress:.1f}%) Прошло: {elapsed/60:.1f} мин | ETA: {eta/60:.1f} мин | Avg: {avg_time:.1f} сек")
            print(f"  Сценарий: {scenario['name']}")
            print(f"  Стиль: {style['name']}, Лейаут: {layout['name']}")
            print(f"  Дисклеймер: {disc_bg['name']}")
            
            try:
                gen_start = time.time()
                image = self.generate_banner(
                    scenario=scenario,
                    headline=headline,
                    description=description,
                    phone=phone,
                    disclaimer=disclaimer,
                    layout=layout,
                    style=style,
                    disclaimer_bg_style=disc_bg,
                    seed=seed,
                    **kwargs,
                )
                gen_time = time.time() - gen_start
                
                # Уникальное имя файла
                timestamp = int(time.time() * 1000) % 100000
                filename = f"bankruptcy_{i:05d}_{scenario['name']}_{style['name']}_{timestamp}.png"
                filepath = output_dir / filename
                
                save_start = time.time()
                image.save(filepath, quality=95)
                save_time = time.time() - save_start
                
                banner_total = time.time() - banner_start
                
                result_entry = {
                    "id": i,
                    "filename": str(filepath),
                    "scenario": scenario['name'],
                    "style": style['name'],
                    "layout": layout['name'],
                    "disclaimer_bg": disc_bg['name'],
                    "headline": headline,
                    "description": description,
                    "seed": seed,
                    "generation_time_sec": round(gen_time, 2),
                    "save_time_sec": round(save_time, 2),
                    "total_time_sec": round(banner_total, 2),
                }
                results.append(result_entry)
                
                timing_stats.append({
                    "id": i,
                    "scenario": scenario['name'],
                    "gen_time": gen_time,
                    "save_time": save_time,
                    "total_time": banner_total,
                })
                
                print(f"Сохранено: {filename} ({gen_time:.1f}s gen + {save_time:.1f}s save)")
                
            except Exception as e:
                errors.append({"id": i, "error": str(e), "scenario": scenario['name']})
                print(f"Ошибка: {e}")
        
        # Итоговая статистика
        total_time = time.time() - start_time
        
        # Расчёт статистики по времени
        if timing_stats:
            gen_times = [t['gen_time'] for t in timing_stats]
            total_times = [t['total_time'] for t in timing_stats]
            
            stats_summary = {
                "run_date": date.today().isoformat(),
                "total_requested": total_count,
                "total_generated": len(results),
                "total_errors": len(errors),
                "total_time_minutes": round(total_time / 60, 2),
                "avg_time_per_banner_sec": round(sum(total_times) / len(total_times), 2),
                "min_time_sec": round(min(total_times), 2),
                "max_time_sec": round(max(total_times), 2),
                "avg_generation_time_sec": round(sum(gen_times) / len(gen_times), 2),
                "parameters": kwargs,
                "banners_per_hour": round(3600 / (sum(total_times) / len(total_times)), 1),
            }
        else:
            stats_summary = {"error": "No banners generated"}
        
        print(f"\n{'='*70}")
        print(f"  ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
        print(f"{'='*70}")
        print(f"Успешно:            {len(results)}/{total_count}")
        print(f" Ошибок:             {len(errors)}")
        print(f"Общее время:        {total_time/60:.1f} минут")
        if timing_stats:
            print(f"Среднее время:      {stats_summary['avg_time_per_banner_sec']:.1f} сек/баннер")
            print(f" Min/Max:            {stats_summary['min_time_sec']:.1f}s / {stats_summary['max_time_sec']:.1f}s")
            print(f" Скорость:           {stats_summary['banners_per_hour']:.0f} баннеров/час")
        print(f"{'='*70}\n")
        
        # Сохраняем детальную статистику
        if save_stats:
            # JSON со всеми данными
            stats_path = output_dir / "generation_stats.json"
            with open(stats_path, "w", encoding="utf-8") as f:
                json.dump({
                    "summary": stats_summary,
                    "timing_details": timing_stats,
                    "errors": errors,
                }, f, indent=2, ensure_ascii=False)
            print(f"📊 Статистика: {stats_path}")
            
            # CSV для удобного анализа
            csv_path = output_dir / "timing_stats.csv"
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("id,scenario,gen_time_sec,save_time_sec,total_time_sec\n")
                for t in timing_stats:
                    f.write(f"{t['id']},{t['scenario']},{t['gen_time']:.2f},{t['save_time']:.2f},{t['total_time']:.2f}\n")
            print(f"📈 CSV для анализа: {csv_path}")
        
        return results
    
    def generate_structured_banner(
        self,
        scenario: Dict[str, Any] = None,
        content: Dict[str, Any] = None,
        phone: str = None,
        disclaimer: str = None,
        style: Dict = None,
        disclaimer_bg_style: Dict = None,
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: int = None,
    ) -> Image.Image:
        """
        Генерация структурированного баннера с маркированными списками.
        
        Формат контента (content):
        {
            "headline": {"main": "...", "sub": "..."},
            "left_block": {"location": "...", "cta": "..."},
            "right_list": {"items": [...], "numbered": True/False},
            "info_block": "..."
        }
        """
        scenario = scenario or random.choice(BANKRUPTCY_SCENARIOS)
        content = content or random.choice(STRUCTURED_CONTENT)
        style = style or random.choice(BANKRUPTCY_STYLES)
        
        # Генерируем фон
        print(f"  Генерация фона: {scenario['name']}...")
        background = self.generate_background(
            scenario=scenario,
            width=width,
            height=height,
            num_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )
        
        # Накладываем структурированный текст
        disc_bg_name = disclaimer_bg_style['name'] if disclaimer_bg_style else "random"
        print(f"  Наложение структурированного текста (стиль: {style['name']})...")
        overlay = BankruptcyBannerOverlay(
            style=style,
            disclaimer_bg_style=disclaimer_bg_style,
            validate=self.validate,
        )
        
        result = overlay.apply_structured(
            background,
            content=content,
            phone=phone,
            disclaimer=disclaimer,
        )
        
        return result
    
    def generate_bullet_banner(
        self,
        scenario: Dict[str, Any] = None,
        bullet_list: Dict[str, Any] = None,
        headline: str = None,
        phone: str = None,
        disclaimer: str = None,
        style: Dict = None,
        disclaimer_bg_style: Dict = None,
        position: str = "right",
        width: int = 1024,
        height: int = 1024,
        num_steps: int = 50,
        guidance_scale: float = 7.5,
        seed: int = None,
    ) -> Image.Image:
        """
        Генерация баннера с маркированным списком.
        
        Args:
            bullet_list: {"title": "...", "items": [...], "position": "left"/"right"}
            position: где разместить список
        """
        scenario = scenario or random.choice(BANKRUPTCY_SCENARIOS)
        bullet_list = bullet_list or random.choice(BULLET_LISTS)
        style = style or random.choice(BANKRUPTCY_STYLES)
        
        # Генерируем фон
        print(f"  Генерация фона: {scenario['name']}...")
        background = self.generate_background(
            scenario=scenario,
            width=width,
            height=height,
            num_steps=num_steps,
            guidance_scale=guidance_scale,
            seed=seed,
        )
        
        # Накладываем текст с маркированным списком
        disc_bg_name = disclaimer_bg_style['name'] if disclaimer_bg_style else "random"
        print(f"  Наложение маркированного списка (позиция: {position})...")
        overlay = BankruptcyBannerOverlay(
            style=style,
            disclaimer_bg_style=disclaimer_bg_style,
            validate=self.validate,
        )
        
        result = overlay.apply_bullet_list(
            background,
            bullet_list=bullet_list,
            headline=headline,
            phone=phone,
            disclaimer=disclaimer,
            position=position,
        )
        
        return result
    
    def generate_mass_structured(
        self,
        output_dir: Path,
        total_count: int = 500,
        banner_type: str = "mixed",  # "structured", "bullet", "mixed"
        save_stats: bool = True,
        **kwargs,
    ) -> List[Dict]:
        """
        Массовая генерация структурированных баннеров.
        
        Args:
            banner_type: 
                - "structured" - только структурированные с правым списком
                - "bullet" - только с маркированными списками
                - "mixed" - смесь всех типов
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        results = []
        errors = []
        timing_stats = []
        start_time = time.time()
        
        print(f"\n{'='*70}")
        print(f"  МАССОВАЯ ГЕНЕРАЦИЯ СТРУКТУРИРОВАННЫХ БАННЕРОВ")
        print(f"  Тип: {banner_type}")
        print(f"  Дата: {date.today().isoformat()}")
        print(f"  Всего: {total_count} баннеров")
        print(f"  Папка: {output_dir}")
        print(f"{'='*70}\n")
        
        for i in range(total_count):
            banner_start = time.time()
            
            # Выбор типа баннера
            if banner_type == "structured":
                use_type = "structured"
            elif banner_type == "bullet":
                use_type = "bullet"
            else:  # mixed
                use_type = random.choice(["simple", "structured", "bullet"])
            
            # Общие параметры
            scenario = random.choice(BANKRUPTCY_SCENARIOS)
            style = random.choice(BANKRUPTCY_STYLES)
            disc_bg = get_random_disclaimer_bg_style()
            seed = random.randint(1, 999999999)
            
            progress = (i + 1) / total_count * 100
            elapsed = time.time() - start_time
            avg_time = elapsed / (i + 1) if i > 0 else 30
            eta = avg_time * (total_count - i - 1)
            
            print(f"\n[{i+1}/{total_count}] ({progress:.1f}%) ETA: {eta/60:.1f} мин")
            print(f"  Тип: {use_type} | Сценарий: {scenario['name']}")
            
            try:
                gen_start = time.time()
                
                if use_type == "structured":
                    content = random.choice(STRUCTURED_CONTENT)
                    image = self.generate_structured_banner(
                        scenario=scenario,
                        content=content,
                        style=style,
                        disclaimer_bg_style=disc_bg,
                        seed=seed,
                        **kwargs,
                    )
                    extra_info = f"content_{STRUCTURED_CONTENT.index(content)}"
                    
                elif use_type == "bullet":
                    bullet_list = random.choice(BULLET_LISTS)
                    headline = random.choice(BANKRUPTCY_HEADLINES)
                    position = bullet_list.get("position", "right")
                    image = self.generate_bullet_banner(
                        scenario=scenario,
                        bullet_list=bullet_list,
                        headline=headline,
                        style=style,
                        disclaimer_bg_style=disc_bg,
                        position=position,
                        seed=seed,
                        **kwargs,
                    )
                    extra_info = f"bullet_{BULLET_LISTS.index(bullet_list)}_{position}"
                    
                else:  # simple
                    headline = random.choice(BANKRUPTCY_HEADLINES)
                    description = random.choice(BANKRUPTCY_DESCRIPTIONS)
                    image = self.generate_banner(
                        scenario=scenario,
                        headline=headline,
                        description=description,
                        style=style,
                        disclaimer_bg_style=disc_bg,
                        seed=seed,
                        **kwargs,
                    )
                    extra_info = "simple"
                
                gen_time = time.time() - gen_start
                
                # Уникальное имя файла
                filename = f"struct_{i:05d}_{use_type}_{scenario['name']}_{seed}.png"
                filepath = output_dir / filename
                
                save_start = time.time()
                image.save(filepath, quality=95)
                save_time = time.time() - save_start
                
                banner_total = time.time() - banner_start
                
                result_entry = {
                    "id": i,
                    "filename": str(filepath),
                    "type": use_type,
                    "scenario": scenario['name'],
                    "style": style['name'],
                    "extra_info": extra_info,
                    "seed": seed,
                    "generation_time_sec": round(gen_time, 2),
                    "total_time_sec": round(banner_total, 2),
                }
                results.append(result_entry)
                
                timing_stats.append({
                    "id": i,
                    "type": use_type,
                    "gen_time": gen_time,
                    "total_time": banner_total,
                })
                
                print(f"  ✅ Сохранено: {filename} ({gen_time:.1f}s)")
                
            except Exception as e:
                errors.append({"id": i, "error": str(e), "type": use_type})
                print(f"  ❌ Ошибка: {e}")
        
        # Итоговая статистика
        total_time = time.time() - start_time
        
        print(f"\n{'='*70}")
        print(f"  ГЕНЕРАЦИЯ ЗАВЕРШЕНА")
        print(f"  📊 Успешно: {len(results)}/{total_count}")
        print(f"  ❌ Ошибок: {len(errors)}")
        print(f"  ⏱️  Время: {total_time/60:.1f} минут")
        print(f"{'='*70}\n")
        
        if save_stats:
            stats_path = output_dir / "structured_stats.json"
            with open(stats_path, "w", encoding="utf-8") as f:
                json.dump({
                    "summary": {
                        "total": total_count,
                        "generated": len(results),
                        "errors": len(errors),
                        "time_minutes": round(total_time / 60, 2),
                        "banner_type": banner_type,
                    },
                    "results": results,
                    "errors": errors,
                }, f, indent=2, ensure_ascii=False)
            print(f"📊 Статистика: {stats_path}")
        
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Генератор баннеров о банкротстве физлиц"
    )
    
    # Сценарии
    parser.add_argument("--scenario", type=str, help="Имя сценария")
    parser.add_argument("--all-scenarios", action="store_true",
                        help="Использовать все сценарии")
    parser.add_argument("--variations", type=int, default=1,
                        help="Вариаций на сценарий")
    
    # Массовая генерация
    parser.add_argument("--mass-generate", type=int, metavar="COUNT",
                        help="Массовая генерация N случайных баннеров (например: --mass-generate 2000)")
    parser.add_argument("--random-all", action="store_true",
                        help="Полностью случайные параметры для каждого баннера")
    
    # Структурированные баннеры (новые!)
    parser.add_argument("--structured", action="store_true",
                        help="Генерировать структурированный баннер с маркированным списком справа")
    parser.add_argument("--bullet-list", action="store_true",
                        help="Генерировать баннер с маркированным списком")
    parser.add_argument("--list-position", type=str, choices=["left", "right"], default="right",
                        help="Позиция маркированного списка")
    parser.add_argument("--mass-structured", type=int, metavar="COUNT",
                        help="Массовая генерация N структурированных баннеров")
    parser.add_argument("--banner-type", type=str, 
                        choices=["structured", "bullet", "mixed"],
                        default="mixed",
                        help="Тип баннеров для массовой генерации")
    
    # Текст
    parser.add_argument("--headline", type=str, help="Заголовок")
    parser.add_argument("--description", type=str, help="Описание")
    parser.add_argument("--phone", type=str, help="Телефон")
    parser.add_argument("--disclaimer", type=str, help="Дисклеймер")
    
    # Стиль
    parser.add_argument("--style", type=str,
                        choices=[s['name'] for s in BANKRUPTCY_STYLES],
                        help="Стиль оформления текста")
    parser.add_argument("--layout", type=str,
                        choices=[l['name'] for l in LAYOUTS],
                        help="Лейаут")
    parser.add_argument("--disclaimer-bg-style", type=str,
                        choices=[s['name'] for s in DISCLAIMER_BG_STYLES],
                        help="Стиль фона дисклеймера")
    
    # Генерация
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--cfg-scale", type=float, default=7.5)
    parser.add_argument("--seed", type=int)
    
    # Модель
    parser.add_argument("--quantize", type=str, choices=["4bit", "8bit"])
    parser.add_argument("--device", type=str, default="cuda")
    parser.add_argument("--dtype", type=str, default="fp16",
                        choices=["fp16", "bf16", "fp32"])
    
    # Валидация
    parser.add_argument("--no-validate", action="store_true",
                        help="Отключить проверку законодательства")
    parser.add_argument("--validate", type=str,
                        help="Проверить текст на запрещённые формулировки")
    
    # Вывод
    parser.add_argument("--output", type=str, default="output/bankruptcy")
    parser.add_argument("--save-metadata", action="store_true")
    
    # Утилиты
    parser.add_argument("--list-scenarios", action="store_true",
                        help="Показать доступные сценарии фонов")
    parser.add_argument("--list-styles", action="store_true",
                        help="Показать стили оформления текста")
    parser.add_argument("--list-disclaimer-styles", action="store_true",
                        help="Показать стили фона дисклеймера")
    parser.add_argument("--list-headlines", action="store_true",
                        help="Показать доступные заголовки")
    parser.add_argument("--list-descriptions", action="store_true",
                        help="Показать доступные описания")
    parser.add_argument("--list-bullet-lists", action="store_true",
                        help="Показать доступные маркированные списки")
    parser.add_argument("--list-structured", action="store_true",
                        help="Показать структурированный контент")
    parser.add_argument("--show-requirements", action="store_true",
                        help="Показать требования законодательства")
    parser.add_argument("--show-stats", action="store_true",
                        help="Показать статистику комбинаций")
    
    args = parser.parse_args()
    
    # Утилиты
    if args.validate:
        violations = TextValidator.check_forbidden(args.validate)
        has_keyword = TextValidator.check_required(args.validate)
        
        print(f"\nПроверка: \"{args.validate}\"")
        print("-" * 50)
        
        if violations:
            print("❌ НАРУШЕНИЯ:")
            for v in violations:
                print(f"   {v}")
        else:
            print("✅ Запрещённых формулировок не найдено")
        
        if has_keyword:
            print("✅ Содержит слово 'банкротство'")
        else:
            print("⚠️  Не содержит слово 'банкротство' (обязательно!)")
        return
    
    if args.list_scenarios:
        print("\n=== Сценарии фонов ===")
        for s in BANKRUPTCY_SCENARIOS:
            print(f"  • {s['name']}")
            print(f"    {s['prompt'][:80]}...")
        return
    
    if args.list_styles:
        print("\n=== Стили оформления текста ===")
        for s in BANKRUPTCY_STYLES:
            print(f"  • {s['name']}: headline={s['headline_color']}")
        return
    
    if args.list_disclaimer_styles:
        print("\n=== Стили фона дисклеймера ===")
        print("\n[Сплошные (solid)]:")
        for s in DISCLAIMER_BG_STYLES:
            if s['type'] == 'solid':
                alpha = s.get('alpha', 160)
                mult = s.get('height_multiplier', 1.0)
                print(f"  • {s['name']}: {s['description']} (alpha={alpha}, x{mult})")
        print("\n[Градиентные (gradient)]:")
        for s in DISCLAIMER_BG_STYLES:
            if s['type'] == 'gradient':
                mult = s.get('height_multiplier', 1.0)
                print(f"  • {s['name']}: {s['description']} (x{mult})")
        return
    
    if args.list_headlines:
        print("\n=== Заголовки (20 вариантов) ===")
        for i, h in enumerate(BANKRUPTCY_HEADLINES, 1):
            print(f"  {i:2d}. {h}")
        return
    
    if args.list_descriptions:
        print("\n=== Описания (20 вариантов) ===")
        for i, d in enumerate(BANKRUPTCY_DESCRIPTIONS, 1):
            print(f"  {i:2d}. {d}")
        return
    
    if args.list_bullet_lists:
        print("\n=== Маркированные списки ===")
        for i, bl in enumerate(BULLET_LISTS, 1):
            pos = bl.get('position', 'right')
            print(f"\n  [{i}] {bl.get('title', 'Без заголовка')} (позиция: {pos})")
            for item in bl.get('items', []):
                print(f"      • {item}")
        return
    
    if args.list_structured:
        print("\n=== Структурированный контент ===")
        for i, sc in enumerate(STRUCTURED_CONTENT, 1):
            hl = sc.get('headline', {})
            main_text = hl.get('main', '').replace('\n', ' ')
            sub_text = hl.get('sub', '')
            print(f"\n  [{i}] {main_text}")
            print(f"      Подзаголовок: {sub_text}")
            
            left = sc.get('left_block', {})
            if left:
                print(f"      Локация: {left.get('location', '').replace(chr(10), ' ')}")
                print(f"      CTA: {left.get('cta', '')}")
            
            right = sc.get('right_list', {})
            if right:
                items = right.get('items', [])
                numbered = "нумерованный" if right.get('numbered') else "маркированный"
                print(f"      Список ({numbered}, {len(items)} пунктов):")
                for item in items[:2]:
                    print(f"          • {item[:50]}...")
            
            if sc.get('info_block'):
                print(f"      Инфо-блок: {sc['info_block'][:40].replace(chr(10), ' ')}...")
        return
    
    if args.show_stats:
        n_scenarios = len(BANKRUPTCY_SCENARIOS)
        n_styles = len(BANKRUPTCY_STYLES)
        n_layouts = len(LAYOUTS)
        n_disc_bg = len(DISCLAIMER_BG_STYLES)
        n_headlines = len(BANKRUPTCY_HEADLINES)
        n_descriptions = len(BANKRUPTCY_DESCRIPTIONS)
        n_bullet_lists = len(BULLET_LISTS)
        n_structured = len(STRUCTURED_CONTENT)
        n_cta = len(CTA_BUTTONS)
        
        total_simple = n_scenarios * n_styles * n_layouts * n_disc_bg * n_headlines * n_descriptions
        total_bullet = n_scenarios * n_styles * n_disc_bg * n_headlines * n_bullet_lists * 2  # 2 позиции
        total_structured = n_scenarios * n_styles * n_disc_bg * n_structured
        total_all = total_simple + total_bullet + total_structured
        
        print(f"""
╔══════════════════════════════════════════════════════════════════╗
║             СТАТИСТИКА КОМБИНАЦИЙ ДЛЯ БАНКРОТСТВА               ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  📊 БАЗОВЫЕ КОМПОНЕНТЫ:                                          ║
║     • Сценарии фонов:     {n_scenarios:3d}                                    ║
║     • Стили текста:        {n_styles:3d}                                    ║
║     • Лейауты:             {n_layouts:3d}                                    ║
║     • Стили дисклеймера:   {n_disc_bg:3d}                                    ║
║     • Заголовки:           {n_headlines:3d}                                    ║
║     • Описания:            {n_descriptions:3d}                                    ║
║                                                                  ║
║  📋 СТРУКТУРИРОВАННЫЙ КОНТЕНТ:                                   ║
║     • Маркированные списки: {n_bullet_lists:3d}                                   ║
║     • Структурированные блоки: {n_structured:3d}                                ║
║     • Кнопки CTA:           {n_cta:3d}                                    ║
║                                                                  ║
║  📈 УНИКАЛЬНЫХ КОМБИНАЦИЙ:                                       ║
║     • Простые баннеры:    {total_simple:,}                             ║
║     • С маркир. списками: {total_bullet:,}                               ║
║     • Структурированные:  {total_structured:,}                                 ║
║     • ВСЕГО:              {total_all:,}                             ║
║                                                                  ║
║  ⏱️  ОЦЕНКА ВРЕМЕНИ (при ~30 сек/баннер):                        ║
║     • 100 баннеров: ~50 минут                                    ║
║     • 500 баннеров: ~4 часа                                      ║
║     • 2000 баннеров: ~17 часов                                   ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
        """)
        return
    
    if args.show_requirements:
        print("""
╔══════════════════════════════════════════════════════════════════╗
║     ТРЕБОВАНИЯ К РЕКЛАМЕ БАНКРОТСТВА ФИЗИЧЕСКИХ ЛИЦ (38-ФЗ)      ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  ✅ ОБЯЗАТЕЛЬНО:                                                 ║
║     • Слово "банкротство" или "банкротство физлиц"               ║
║     • С 01.09.2025: предупредительная надпись                    ║
║     • С 01.01.2026: предупреждение о последствиях +              ║
║                     информация о льготных вариантах              ║
║                                                                  ║
║  ❌ ЗАПРЕЩЕНО:                                                   ║
║     • "спишем долги", "списание долгов"                          ║
║     • "избавим от долгов", "закроем долги"                       ║
║     • "гарантированно", "100%", "навсегда"                       ║
║     • "через суд", "без суда"                                    ║
║     • Обещания освобождения от обязательств                      ║
║     • Призывы не платить по долгам                               ║
║     • Банкротство юрлиц (только физлица!)                        ║
║                                                                  ║
║  📋 ДИСКЛЕЙМЕРЫ:                                                 ║
║     • До 01.09.2025: стандартный                                 ║
║     • С 01.09.2025: ВНИМАНИЕ! + предупреждение                   ║
║     • С 01.01.2026: последствия + МФЦ/бесплатные варианты        ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
        """)
        return
    
    # Типы данных
    dtype_map = {"fp16": torch.float16, "bf16": torch.bfloat16, "fp32": torch.float32}
    dtype = dtype_map[args.dtype]
    
    # Создаём пайплайн
    pipeline = BankruptcyBannerPipeline(
        device=args.device,
        dtype=dtype,
        quantize=args.quantize,
        validate=not args.no_validate,
    )
    
    output_dir = Path(args.output)
    
    # === МАССОВАЯ ГЕНЕРАЦИЯ ===
    if args.mass_generate:
        print(f"\n🚀 ЗАПУСК МАССОВОЙ ГЕНЕРАЦИИ: {args.mass_generate} баннеров")
        
        results = pipeline.generate_mass_random(
            output_dir=output_dir,
            total_count=args.mass_generate,
            width=args.width,
            height=args.height,
            num_steps=args.steps,
            guidance_scale=args.cfg_scale,
        )
        
        # Сохраняем метаданные
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"📄 Метаданные: {metadata_path}")
        
        return
    
    # === МАССОВАЯ ГЕНЕРАЦИЯ СТРУКТУРИРОВАННЫХ БАННЕРОВ ===
    if args.mass_structured:
        print(f"\n🚀 ЗАПУСК СТРУКТУРИРОВАННОЙ ГЕНЕРАЦИИ: {args.mass_structured} баннеров")
        print(f"   Тип: {args.banner_type}")
        
        results = pipeline.generate_mass_structured(
            output_dir=output_dir,
            total_count=args.mass_structured,
            banner_type=args.banner_type,
            width=args.width,
            height=args.height,
            num_steps=args.steps,
            guidance_scale=args.cfg_scale,
        )
        
        print(f"\n✅ Создано {len(results)} структурированных баннеров в {output_dir}")
        return
    
    # === ОДИН СТРУКТУРИРОВАННЫЙ БАННЕР ===
    if args.structured:
        print("\n🚀 Генерация структурированного баннера...")
        
        # Выбор сценария
        if args.scenario:
            scenario = next((s for s in BANKRUPTCY_SCENARIOS if s['name'] == args.scenario), None)
            if not scenario:
                print(f"Сценарий '{args.scenario}' не найден!")
                return
        else:
            scenario = random.choice(BANKRUPTCY_SCENARIOS)
        
        style = None
        if args.style:
            style = next((s for s in BANKRUPTCY_STYLES if s['name'] == args.style), None)
        
        content = random.choice(STRUCTURED_CONTENT)
        
        image = pipeline.generate_structured_banner(
            scenario=scenario,
            content=content,
            style=style,
            width=args.width,
            height=args.height,
            num_steps=args.steps,
            guidance_scale=args.cfg_scale,
            seed=args.seed,
        )
        
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"structured_{scenario['name']}_{args.seed or 'random'}.png"
        image.save(filepath, quality=95)
        print(f"✅ Сохранено: {filepath}")
        return
    
    # === ОДИН БАННЕР С МАРКИРОВАННЫМ СПИСКОМ ===
    if args.bullet_list:
        print("\n🚀 Генерация баннера с маркированным списком...")
        
        # Выбор сценария
        if args.scenario:
            scenario = next((s for s in BANKRUPTCY_SCENARIOS if s['name'] == args.scenario), None)
            if not scenario:
                print(f"Сценарий '{args.scenario}' не найден!")
                return
        else:
            scenario = random.choice(BANKRUPTCY_SCENARIOS)
        
        style = None
        if args.style:
            style = next((s for s in BANKRUPTCY_STYLES if s['name'] == args.style), None)
        
        bullet_list = random.choice(BULLET_LISTS)
        
        image = pipeline.generate_bullet_banner(
            scenario=scenario,
            bullet_list=bullet_list,
            headline=args.headline,
            style=style,
            position=args.list_position,
            width=args.width,
            height=args.height,
            num_steps=args.steps,
            guidance_scale=args.cfg_scale,
            seed=args.seed,
        )
        
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"bullet_{scenario['name']}_{args.list_position}_{args.seed or 'random'}.png"
        image.save(filepath, quality=95)
        print(f"✅ Сохранено: {filepath}")
        return
    
    # === ОБЫЧНАЯ ГЕНЕРАЦИЯ ===
    # Выбор сценариев
    if args.all_scenarios:
        scenarios = BANKRUPTCY_SCENARIOS
    elif args.scenario:
        scenarios = [s for s in BANKRUPTCY_SCENARIOS if s['name'] == args.scenario]
        if not scenarios:
            print(f"Сценарий '{args.scenario}' не найден!")
            print("Доступные:", [s['name'] for s in BANKRUPTCY_SCENARIOS])
            return
    else:
        scenarios = [BANKRUPTCY_SCENARIOS[0]]
    
    # Стиль/лейаут
    style = None
    if args.style:
        for s in BANKRUPTCY_STYLES:
            if s['name'] == args.style:
                style = s
                break
    
    layout = get_layout_by_name(args.layout) if args.layout else None
    
    # Стиль фона дисклеймера
    disclaimer_bg_style = None
    if args.disclaimer_bg_style:
        disclaimer_bg_style = get_disclaimer_bg_style_by_name(args.disclaimer_bg_style)
    
    # Генерация
    results = pipeline.generate_batch(
        scenarios=scenarios,
        output_dir=output_dir,
        variations=args.variations,
        headline=args.headline,
        description=args.description,
        phone=args.phone,
        disclaimer=args.disclaimer,
        layout=layout,
        style=style,
        disclaimer_bg_style=disclaimer_bg_style,
        width=args.width,
        height=args.height,
        num_steps=args.steps,
        guidance_scale=args.cfg_scale,
        seed=args.seed,
    )
    
    # Метаданные
    if args.save_metadata:
        metadata_path = output_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n📄 Метаданные: {metadata_path}")
    
    print(f"\n✅ Создано {len(results)} баннеров в {output_dir}")


if __name__ == "__main__":
    main()
