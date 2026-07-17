# GLM-Image Pipeline

Каркас GLM-Image (AR → VQ → DiT → VAE), **Simple Mode (SDXL)** API и рабочие **category-пайплайны** рекламных баннеров.
Веса GLM и медиа (пачки, шрифты, логотипы) в git не входят.

## Режимы

| Режим | Готовность | Backend |
|-------|------------|---------|
| Simple / API | GPU + HF SDXL | `pipeline/inference/simple_pipeline.py`, `serving.api.server` |
| Category banners | GPU + media via symlink | `scripts/generate_*_banners.py` |
| Full GLM | нужны AR/DiT/VQ checkpoints | `pipeline/inference/pipeline.py` (без весов — tiny mock) |

## Быстрый старт (каркас + API)

```bash
cd glm-image-pipeline
python -m venv .venv && source .venv/bin/activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
python scripts/smoke_check.py

python scripts/generate.py --simple --prompt 'A poster with text "Hello"' --output outputs
python -m serving.api.server --port 8080
docker compose up --build
```

## Category runtime (как в проде)

Код и JSON — в репозитории. Медиа — снаружи:

```bash
# По умолчанию линкует из /mldata/glm-image-pipeline
bash scripts/link_runtime_data.sh

# Или свой каталог с cigarette_images/, fonts/, baby_logo/
export GLM_DATA_ROOT=/path/to/media-tree
bash scripts/link_runtime_data.sh
```

| Категория | Entrypoint | Конфиг / данные |
|-----------|------------|-----------------|
| Tobacco | `scripts/generate_tobacco_banners.py` | `configs/tobacco*.json`, `cigarette_images/`, `fonts/craft/` |
| Alcomarket | `scripts/generate_alcomarket_banners.py` | `configs/alcomarket_config.json` |
| Bankruptcy | `scripts/generate_bankruptcy_banners.py` (+ `_2`, `_with_qr`) | `configs/bankruptcy_config.json` |
| Folk medicine | `scripts/generate_folk_medicine_banners.py` (+ QR) | `configs/folk_medicine_config.json` |
| Lombard | `scripts/generate_lombard_banners.py` | `scripts/lombard_companies.json` |
| Trust | `scripts/generate_trust_management_banners.py` | `scripts/trust_management_companies.json` |
| Baby food | `scripts/generate_baby_food_banners.py` | `scripts/baby_food_*.json`, `baby_logo/` |
| Discreditation | `scripts/generate_discreditation_banners.py` | `configs/discreditation_config.json` |
| Circular frame | `scripts/generate_circular_frame_banners.py` | `configs/circular_frame_config.json` |

QR-категории: внешний `/mldata/custom-qr-generator` (не в этом репо). См. `scripts/*README.md`.

Базовый оверлей: `scripts/text_overlay.py`. Общие баннеры: `generate_banners.py`, `generate_ad_banners.py`.

## Serving / прод-обвязка

- `configs/serving_config.yaml` → CORS, rate limit, auth, `max_concurrent`, max resolution
- Env: `.env.example` (`GLM_API_KEY`, `GLM_MAX_CONCURRENT`, `GLM_OUTPUT_DIR`, `GLM_DATA_ROOT`)
- `/health`, `/ready`; инференс через семафор (1 GPU / процесс)
- `/i2i` — SDXL Img2Img; `return_base64=false` → файлы в `outputs/api/`
- Масштаб: N реплик API × 1 GPU; AR/DiT/VQ в YAML — целевая схема, отдельные серверы не в срезе

## Структура

```
configs/     model/vq/training/serving + category JSON
models/      архитектуры (без весов)
pipeline/    inference + training
serving/     FastAPI + vLLM launcher
scripts/     CLI категорий, overlays, link_runtime_data, smoke_check
Dockerfile, docker-compose.yaml
```

## Ограничения

- `cigarette_images/`, `fonts/`, `baby_logo/` — symlink, не commit (см. `.gitignore`)
- `torch` ставить под свою CUDA; full stack: `requirements-full.txt`
- Full GLM без checkpoints — tiny mock, не качество
