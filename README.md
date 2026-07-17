# GLM-Image Pipeline

Каркас GLM-Image (AR → VQ → DiT → VAE) и рабочий **Simple Mode** на SDXL.
Полные веса GLM-Image в репозитории не публикуются — без checkpoints Full mode только mock/tiny.

## Режимы

| Режим | Готовность | Backend |
|-------|------------|---------|
| Simple | работает при наличии GPU + HF-кэша SDXL | `pipeline/inference/simple_pipeline.py` |
| Full GLM | нужны AR/DiT/VQ checkpoints | `pipeline/inference/pipeline.py` |

API (`serving.api.server`) по умолчанию обслуживает **Simple Mode (SDXL)**, не GLM.

## Быстрый старт

```bash
cd glm-image-pipeline
python -m venv .venv && source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

# Offline smoke (без GPU / без скачивания весов)
python scripts/smoke_check.py

# Генерация (SDXL)
python scripts/generate.py --simple --prompt 'A poster with text "Hello"' --output outputs

# API
python -m serving.api.server --port 8080
# http://localhost:8080/docs  /health  /ready

# Docker (GPU)
docker compose up --build
```

Обучение / vLLM / OCR: `pip install -r requirements-full.txt`.

## Структура

```
configs/          YAML (model, vq, training, serving)
models/           архитектуры VQ / AR / DiT / Glyph (без весов)
pipeline/         inference + training
serving/api/      FastAPI gateway
serving/vllm_backend/  заготовка AR через vLLM
scripts/          generate*, text_overlay, smoke_check
Dockerfile, docker-compose.yaml
```

Баннеры: `scripts/generate_banners.py`, `scripts/generate_ad_banners.py`, `scripts/text_overlay.py`.

## Serving / прод

- Конфиг: `configs/serving_config.yaml` (читается API: CORS, rate limit, auth, max resolution, `max_concurrent`).
- Env: см. `.env.example` (`GLM_API_KEY`, `GLM_MAX_CONCURRENT`, `GLM_OUTPUT_DIR`).
- `/health` — liveness; `/ready` — процесс поднят (модель грузится lazy).
- Инференс сериализуется семафором (`GLM_MAX_CONCURRENT`, default 1) — один GPU-процесс без дублирования весов через `workers>1`.
- `POST /i2i` — реальный SDXL Img2Img (не stub).
- `return_base64=false` — сохранение в `outputs/api/` и путь в ответе.
- Rate limit / API key — выключаются в YAML; для прода включить `auth.enabled` или `GLM_API_KEY`.

Масштабирование: несколько реплик API за балансировщиком + по одному GPU на реплику; AR/DiT/VQ микросервисы в `serving_config.yaml` — целевая схема, отдельные `dit_server`/`vq_server` в этом срезе не реализованы.

## Full GLM без весов

Mock использует **tiny** AR/DiT (не 2B/9B), чтобы не OOM. Качество нерепрезентативно. Контракт AR: `generate_image_tokens` → `{"vq_tokens": ...}`.

## Документация

- `QUICKSTART.md` — CLI/API примеры
- `TRAINING.md` — стадии обучения (части скриптов датасетов могут отсутствовать — см. smoke)

## Ограничения

- Веса GLM не входят в git; `output/`/`outputs/`/`checkpoints/` в `.gitignore`.
- `torch` не закреплён в `requirements.txt` — ставить под свою CUDA.
- vLLM backend и multi-GPU DiT — заготовки под обученные checkpoints.
