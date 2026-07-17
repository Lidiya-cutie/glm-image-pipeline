# GLM-Image Pipeline - Quick Start Guide

## 🚀 Быстрый запуск (работает из коробки)

### 1. Установка зависимостей

```bash
cd glm-image-pipeline
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
python scripts/smoke_check.py
```

### 2. Генерация изображений (Simple Mode)

**Этот режим работает сразу** - использует Stable Diffusion XL:

```bash
# Простая генерация
python scripts/generate.py \
    --prompt "A movie poster with text \"The Matrix\" in green neon style" \
    --simple \
    --output outputs

# С настройками
python scripts/generate.py \
    --prompt "Professional banner with \"SALE 50% OFF\" bold red text" \
    --simple \
    --width 1280 \
    --height 720 \
    --steps 50 \
    --cfg-scale 9.0 \
    --seed 42 \
    --output outputs
```

### 3. Запуск API сервера

```bash
# Запуск сервера
python -m serving.api.server --port 8080

# API доступен на http://localhost:8080
# Документация: http://localhost:8080/docs
```

**Пример запроса:**
```bash
curl -X POST http://localhost:8080/generate \
    -H "Content-Type: application/json" \
    -d '{
        "prompt": "A poster with text \"Hello World\"",
        "width": 1024,
        "height": 1024,
        "num_inference_steps": 50
    }'
```

---

## 📊 Что на выходе

1. **Изображения** в формате PNG/JPG/WebP
2. **Метаданные**: seed, параметры генерации
3. **API Response** (JSON с base64 изображениями)

---

## 🏗️ Полный GLM-Image пайплайн (требует обучения)

### Архитектура

```
┌─────────────────────────────────────────────────────────────────────┐
│                     GLM-Image Full Pipeline                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  "Create poster with 'Hello'"                                        │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │ GLM Tokenizer   │  → text tokens [BOS, t1, t2, ..., IMAGE_START] │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │ AR Model (9B)   │  → VQ tokens (64×64 = 4096 tokens)             │
│  │ Autoregressive  │     Содержат: layout, семантику, композицию    │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │ VQ Codebook     │  → VQ embeddings [4096, 1024]                  │
│  │ (16384 codes)   │                                                │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │ DiT Decoder(7B) │  → latents [4, 128, 128]                       │
│  │ + Text Embeds   │     50 diffusion steps                         │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│  ┌─────────────────┐                                                │
│  │ VAE Decoder     │  → image [3, 1024, 1024]                       │
│  └────────┬────────┘                                                │
│           │                                                          │
│           ▼                                                          │
│       PNG Image                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Для полного пайплайна нужно:

1. **Обучить VQ Encoder** на большом датасете изображений
2. **Дообучить AR Model** (из GLM-4-9B) на парах (text, vq_tokens)
3. **Обучить DiT Decoder** на (vq_tokens, text) → image
4. **RL Fine-tuning** с Glyph Encoder для точного текста

### Запуск полного пайплайна (с весами):

```bash
python scripts/generate.py \
    --prompt "A poster with text \"Hello World\"" \
    --ar-model checkpoints/ar-model \
    --dit-model checkpoints/dit-model \
    --vq-model checkpoints/vq-model \
    --width 1024 \
    --height 1024
```

---

## 🔧 Продакшн-деплой с vLLM

### Микросервисная архитектура

```
┌─────────────────────────────────────────────────────────────────┐
│                      API Gateway (:8080)                         │
│                            │                                     │
│        ┌──────────────────┼──────────────────┐                  │
│        ▼                  ▼                  ▼                  │
│  ┌──────────┐      ┌──────────┐       ┌──────────┐             │
│  │ vLLM AR  │      │   DiT    │       │   VQ     │             │
│  │ (:8000)  │      │ (:8001)  │       │ (:8002)  │             │
│  │ 4×A100   │      │ 4×A100   │       │ 1×A100   │             │
│  └──────────┘      └──────────┘       └──────────┘             │
└─────────────────────────────────────────────────────────────────┘
```

### Запуск через vLLM (нужны checkpoints):

```bash
# AR Server (требует обученные веса)
python -m serving.vllm_backend.launcher \
    --model checkpoints/ar-model \
    --port 8000 \
    --tensor-parallel 4

# Отдельный serving.dit_server в этом срезе НЕ реализован.
# API gateway по умолчанию = SDXL Simple Mode:
python -m serving.api.server --port 8080

# Или Docker (GPU):
docker compose up --build
```

---

## 📁 Структура проекта

```
glm-image-pipeline/
├── configs/                    # Конфигурации
│   ├── model_config.yaml       # Параметры моделей
│   ├── vq_config.yaml          # VQ кодбук (16384×1024)
│   ├── training_config.yaml    # Обучение + GRPO
│   └── serving_config.yaml     # vLLM + API
│
├── models/                     # Архитектуры
│   ├── vq_encoder/             # VQ: encoder, decoder, codebook
│   ├── ar_model/               # AR 9B (из GLM-4)
│   ├── dit_decoder/            # DiT 7B + samplers
│   └── glyph_encoder/          # OCR для RL
│
├── pipeline/                   # Пайплайны
│   └── inference/
│       ├── simple_pipeline.py  # SDXL (работает сразу)
│       └── pipeline.py         # Полный GLM-Image
│
├── serving/                    # Продакшн
│   ├── api/server.py           # REST API
│   └── vllm_backend/           # vLLM интеграция
│
├── scripts/
│   └── generate.py             # CLI для генерации
│
└── requirements.txt
```

---

## 🔢 Ключевые параметры

### VQ Codebook
- **Размер**: 16384 кодов (2^14)
- **Embedding dim**: 1024
- **Grid**: image_size / 16 (для 1024×1024 → 64×64 = 4096 токенов)

### AR Model (9B)
- **Base**: GLM-4-9B-0414
- **Vocab**: 151552 (text) + 16384 (VQ) = 167936
- **Max seq**: 131072

### DiT Decoder (7B)
- **Hidden**: 3072
- **Layers**: 32
- **Heads**: 24
- **Diffusion**: Flow Matching, 50 steps

---

## ⚠️ Ограничения текущей версии

1. **Simple Mode** - работает из коробки, но это обычный SDXL
2. **Full Pipeline** - требует обученных весов (AR 9B, DiT 7B, VQ)
3. **Веса GLM-Image не опубликованы** - нужно обучать самостоятельно

### Альтернативы для production:
- Использовать SDXL/Flux с промпт-инжинирингом для текста
- Дообучить LoRA для конкретных задач
- Ждать официальные веса от Z.AI
