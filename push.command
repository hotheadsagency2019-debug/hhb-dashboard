#!/bin/bash
# HHB Dashboard — одним кликом запушить все изменения
cd "$(dirname "$0")"

echo "📦 Добавляем изменения..."
git add -A

# Проверяем есть ли что коммитить
if git diff --cached --quiet; then
  echo "✅ Нет изменений для коммита"
else
  TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
  git commit -m "update: $TIMESTAMP"
  echo "✅ Коммит создан"

  echo "🚀 Пушим в GitHub..."
  git push

  echo ""
  echo "✅ Готово! Дашборд обновится через ~1 минуту:"
  echo "   https://hotheadsagency2019-debug.github.io/hhb-dashboard/"
fi

echo ""
echo "Нажми Enter чтобы закрыть..."
read
