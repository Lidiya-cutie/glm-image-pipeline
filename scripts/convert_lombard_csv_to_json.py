#!/usr/bin/env python3
"""
Конвертация CSV файла с данными ломбардов в JSON формат.
"""

import csv
import json
from pathlib import Path
from collections import defaultdict

CSV_PATH = Path(__file__).parent / "lombard_comp.csv"
JSON_PATH = Path(__file__).parent / "lombard_companies.json"


def convert_csv_to_json():
    """Конвертирует CSV в JSON, группируя филиалы по одной компании."""
    
    companies = {}
    
    with open(CSV_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        for row in reader:
            full_name = row['Full_Name'].strip()
            website = row['Website'].strip()
            phone = row['Phone'].strip()
            address = row['Address'].strip()
            short_name = row['Short_Name'].strip()
            
            # Если компания уже есть, обновляем данные (берем первый телефон и сайт)
            if full_name not in companies:
                companies[full_name] = {
                    "website": website,
                    "phone": phone,
                    "address": address,
                    "short_name": short_name,
                }
            else:
                # Если телефон или сайт пустые, но есть в новой записи - обновляем
                if not companies[full_name].get("phone") and phone:
                    companies[full_name]["phone"] = phone
                if not companies[full_name].get("website") and website:
                    companies[full_name]["website"] = website
    
    # Сохраняем в JSON
    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(companies, f, ensure_ascii=False, indent=4)
    
    print(f"✅ Конвертировано {len(companies)} уникальных компаний из CSV в JSON")
    print(f"📁 Сохранено в: {JSON_PATH}")
    
    # Показываем первые 5 компаний для проверки
    print("\nПримеры компаний:")
    for i, (name, data) in enumerate(list(companies.items())[:5]):
        print(f"  {i+1}. {name}")
        print(f"     Телефон: {data.get('phone', 'N/A')}")
        print(f"     Сайт: {data.get('website', 'N/A')}")


if __name__ == "__main__":
    convert_csv_to_json()
