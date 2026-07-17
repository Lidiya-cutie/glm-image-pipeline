#!/usr/bin/env python3
"""
Конвертация CSV с данными производителей детского питания в JSON.

По аналогии с convert_lombard_csv_to_json.py:
- Вход: scripts/baby_food.csv (Category, Mark, Full_name, INN, OGRN, Аdress, Phone, Site)
- Выход: scripts/baby_food_companies.json

Структура JSON:
- Ключ — полное наименование юридического лица (Full_name).
- Значение: marks (торговые названия для заголовка), full_name, inn, ogrn, address, phone, site
  для подстановки в полный дисклеймер.

Один и тот же производитель (Full_name) может иметь несколько торговых марок (Mark);
они объединяются в список marks. Заголовок баннера можно формировать из случайного mark.
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict

CSV_PATH = Path(__file__).parent / "baby_food.csv"
JSON_PATH = Path(__file__).parent / "baby_food_companies.json"


def _strip(s: str) -> str:
    return (s or "").strip()


def _norm_inn_ogrn(s: str) -> str:
    """Убирает пробелы из числовых полей."""
    return _strip(s).replace(" ", "")


def convert_csv_to_json() -> None:
    """Читает baby_food.csv, группирует по Full_name, сохраняет в baby_food_companies.json."""
    companies: Dict[str, Dict[str, Any]] = {}

    # Столбцы CSV: Category=0, Mark=1, Full_name=2, INN=3, OGRN=4, Аdress=5, Phone=6, Site=7
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.reader(f, skipinitialspace=True)
        next(reader)  # заголовок

        for row in reader:
            if len(row) < 8:
                continue
            full_name = _strip(row[2])
            mark = _strip(row[1])
            if not full_name:
                continue

            inn = _norm_inn_ogrn(row[3])
            ogrn = _norm_inn_ogrn(row[4])
            address = _strip(row[5])
            phone = _strip(row[6])
            site = _strip(row[7])

            if full_name not in companies:
                companies[full_name] = {
                    "marks": [],
                    "full_name": full_name,
                    "inn": inn,
                    "ogrn": ogrn,
                    "address": address,
                    "phone": phone,
                    "site": site,
                }
            if mark and mark not in companies[full_name]["marks"]:
                companies[full_name]["marks"].append(mark)
            # Обновляем контакты, если в новой строке они заполнены, а старые пустые
            if not companies[full_name]["phone"] and phone:
                companies[full_name]["phone"] = phone
            if not companies[full_name]["site"] and site:
                companies[full_name]["site"] = site
            if not companies[full_name]["address"] and address:
                companies[full_name]["address"] = address

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(companies, f, ensure_ascii=False, indent=2)

    print(f"✅ Конвертировано {len(companies)} производителей из {CSV_PATH.name} в {JSON_PATH.name}")
    print(f"📁 Файл: {JSON_PATH}")
    print("\nПримеры (mark — для заголовка, остальное — для полного дисклеймера):")
    for i, (name, data) in enumerate(list(companies.items())[:5]):
        marks = data.get("marks", [])
        print(f"  {i+1}. {name}")
        print(f"     Марки (заголовок): {marks[:3]}{'…' if len(marks) > 3 else ''}")
        print(f"     ИНН: {data.get('inn')}, ОГРН: {data.get('ogrn')}")
        print(f"     Телефон: {data.get('phone', '') or '—'}")
        print(f"     Сайт: {data.get('site', '') or '—'}")


if __name__ == "__main__":
    convert_csv_to_json()
