# GLM-Image Training Guide

Полное руководство по обучению всех компонентов GLM-Image.

## 📋 Обзор этапов обучения

```
┌─────────────────────────────────────────────────────────────────────┐
│                    Training Pipeline                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Stage 1: VQ Encoder (2-4 недели)                                   │
│     └─► Обучаем сжимать изображения в дискретные токены             │
│                                                                      │
│  Stage 2: AR Model (2-4 недели)                                     │
│     └─► Обучаем генерировать VQ токены по тексту                    │
│                                                                      │
│  Stage 3: DiT Decoder (2-4 недели)                                  │
│     └─► Обучаем восстанавливать изображения из VQ токенов           │
│                                                                      │
│  Stage 4: RL Fine-tuning (1-2 недели)                               │
│     └─► GRPO для улучшения качества текста                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## 💾 Требования

### Hardware
| Этап | GPU | VRAM | Время |
|------|-----|------|-------|
| VQ Encoder | 8× A100 | 40GB each | 3-5 дней |
| AR Model | 8× A100 | 80GB each | 1-2 недели |
| DiT Decoder | 8× A100 | 80GB each | 1-2 недели |
| RL Fine-tuning | 8× A100 | 80GB each | 3-5 дней |

### Данные
| Датасет | Размер | Назначение |
|---------|--------|------------|
| LAION-Aesthetics | 600M images | Общее качество |
| Text-rich images | 10-50M images | Текст на изображениях |
| Posters/Banners | 1-5M images | Layout и дизайн |

---

## Stage 1: Обучение VQ Encoder

### 1.1 Подготовка данных

```bash
# Скачать LAION-Aesthetics subset
python scripts/data/download_laion.py \
    --output data/laion \
    --aesthetic-score 6.0 \
    --num-samples 10000000

# Или использовать свой датасет
# Структура: data/images/*.jpg + data/captions.json
```

### 1.2 Запуск обучения VQ

```bash
python -m pipeline.training.train_vq \
    --config configs/vq_config.yaml \
    --data-dir data/laion \
    --output-dir checkpoints/vq-encoder \
    --batch-size 32 \
    --num-epochs 100 \
    --num-gpus 8
```

### 1.3 Валидация VQ

```bash
python scripts/validate_vq.py \
    --checkpoint checkpoints/vq-encoder/best.pt \
    --test-images data/test/*.jpg \
    --output results/vq-validation
```

**Метрики для VQ:**
- Reconstruction MSE < 0.01
- Perplexity > 1000 (использование кодбука)
- FID < 10 (качество реконструкции)

---

## Stage 2: Обучение AR Model

### 2.1 Подготовка данных с VQ токенами

```bash
# Энкодировать все изображения в VQ токены
python scripts/data/encode_to_vq.py \
    --vq-checkpoint checkpoints/vq-encoder/best.pt \
    --images-dir data/laion \
    --output data/vq-tokens \
    --num-workers 32
```

### 2.2 Запуск обучения AR

```bash
# Инициализация из GLM-4
python -m pipeline.training.train_ar \
    --config configs/training_config.yaml \
    --base-model THUDM/glm-4-9b-chat \
    --data-dir data/vq-tokens \
    --output-dir checkpoints/ar-model \
    --batch-size 8 \
    --gradient-accumulation 16 \
    --num-epochs 50 \
    --deepspeed configs/deepspeed_zero3.json
```

**Метрики для AR:**
- Cross-entropy loss < 2.0
- Token accuracy > 60%
- Perplexity < 50

---

## Stage 3: Обучение DiT Decoder

### 3.1 Подготовка данных

```bash
# Создать пары (image, vq_tokens, text) для DiT
python scripts/data/prepare_dit_data.py \
    --images-dir data/laion \
    --vq-tokens-dir data/vq-tokens \
    --captions data/captions.json \
    --output data/dit-training
```

### 3.2 Запуск обучения DiT

```bash
python -m pipeline.training.train_dit \
    --config configs/training_config.yaml \
    --vq-checkpoint checkpoints/vq-encoder/best.pt \
    --data-dir data/dit-training \
    --output-dir checkpoints/dit-model \
    --batch-size 4 \
    --gradient-accumulation 8 \
    --num-epochs 100
```

**Метрики для DiT:**
- MSE loss < 0.05
- FID < 15
- CLIP score > 0.30

---

## Stage 4: RL Fine-tuning (GRPO)

### 4.1 Запуск GRPO для AR

```bash
python -m pipeline.training.train_grpo_ar \
    --ar-checkpoint checkpoints/ar-model/best.pt \
    --dit-checkpoint checkpoints/dit-model/best.pt \
    --vq-checkpoint checkpoints/vq-encoder/best.pt \
    --prompts data/rl-prompts.json \
    --output-dir checkpoints/ar-model-grpo \
    --num-iterations 10000
```

### 4.2 Запуск Flow-GRPO для DiT

```bash
python -m pipeline.training.train_grpo_dit \
    --dit-checkpoint checkpoints/dit-model/best.pt \
    --ar-checkpoint checkpoints/ar-model-grpo/best.pt \
    --vq-checkpoint checkpoints/vq-encoder/best.pt \
    --prompts data/rl-prompts.json \
    --output-dir checkpoints/dit-model-grpo \
    --num-iterations 10000
```

---

## 🔧 Быстрый старт (минимальный пайплайн на 1 GPU)

Для тестирования на небольшом датасете (1 GPU, ~24GB VRAM):

```bash
# 1. Подготовить тестовые данные (свои изображения)
mkdir -p data/sample/images
# Положить изображения в data/sample/images/

# Создать captions.json:
# [{"file_name": "image1.jpg", "caption": "A poster with text Hello"}]

# 2. Обучить VQ (уменьшенная версия ~1 день)
python -m pipeline.training.train_vq \
    --config configs/vq_config.yaml \
    --data-dir data/sample/images \
    --output-dir checkpoints/vq-small \
    --batch-size 8 \
    --num-epochs 50 \
    --image-size 512

# 3. Энкодировать изображения в VQ токены
python scripts/data/encode_to_vq.py \
    --vq-checkpoint checkpoints/vq-small/best.pt \
    --images-dir data/sample/images \
    --captions data/sample/captions.json \
    --output data/vq-tokens \
    --image-size 512

# 4. Обучить AR (GPT-2 как base, ~2 дня)
python -m pipeline.training.train_ar \
    --config configs/training_config.yaml \
    --base-model gpt2-medium \
    --data-dir data/vq-tokens \
    --output-dir checkpoints/ar-small \
    --batch-size 2 \
    --num-epochs 20

# 5. Обучить DiT (~3 дня)
python -m pipeline.training.train_dit \
    --vq-checkpoint checkpoints/vq-small/best.pt \
    --data-dir data/sample/images \
    --output-dir checkpoints/dit-small \
    --batch-size 2 \
    --num-epochs 50

# 6. Тест генерации
python scripts/generate.py \
    --ar-model checkpoints/ar-small/best.pt \
    --dit-model checkpoints/dit-small/best.pt \
    --vq-model checkpoints/vq-small/best.pt \
    --prompt "A poster with text \"Hello World\""
```

---

## 📊 Минимальные датасеты для тестирования

| Датасет | Размер | Где взять |
|---------|--------|-----------|
| TextOCR | 900K images | [link](https://textvqa.org/textocr/) |
| SynthText | 800K images | [link](https://github.com/ankush-me/SynthText) |
| COCO-Text | 63K images | [link](https://bgshih.github.io/cocotext/) |
| Свои данные | 10K+ images | Постеры, баннеры, UI |

---

## ⚠️ Важные замечания

1. **Полное обучение GLM-Image (9B+7B)** требует:
   - 8× A100 80GB
   - ~100M изображений
   - ~1 месяц времени

2. **Для практических задач** рекомендуется:
   - Использовать меньшие модели (GPT-2 + DiT-S)
   - Fine-tune на специфичном домене
   - 10K-100K изображений достаточно для узкой задачи

3. **Альтернативы** если нет ресурсов:
   - SDXL + prompt engineering
   - LoRA fine-tuning существующих моделей
   - Использовать API (Midjourney, DALL-E)
