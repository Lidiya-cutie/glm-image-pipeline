#!/bin/bash
# Скрипт для установки зависимостей QR генератора

echo "Установка зависимостей для QR генератора..."
echo ""

# Проверка наличия pip
if ! command -v pip3 &> /dev/null; then
    echo "❌ pip3 не найден. Установите pip3 сначала."
    exit 1
fi

# Установка базовых зависимостей
echo "📦 Установка qrcode и Pillow..."
pip3 install qrcode[pil]>=7.4.2 Pillow>=10.0.0

# Проверка установки
echo ""
echo "Проверка установки..."
python3 -c "import qrcode; import PIL; print('✅ Все зависимости установлены успешно!')" 2>&1

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Готово! Теперь можно запускать generate_bankruptcy_with_qr.py"
else
    echo ""
    echo "❌ Ошибка при проверке. Попробуйте установить вручную:"
    echo "   pip3 install qrcode[pil] Pillow"
fi
