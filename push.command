#!/bin/bash
# HHB Dashboard — одним кликом пушить ВСЕ изменения
cd "$(dirname "$0")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " HHB Dashboard — Push"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

git add -A

if git diff --cached --quiet; then
  echo "✅ Нет изменений — всё актуально"
else
  TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
  git commit -m "update: $TIMESTAMP"
  echo ""
  echo "🚀 Пушим в GitHub..."
  git push
  echo ""
  echo "✅ Готово! GitHub Actions запустит обновление дашборда."
  echo "   Через ~1 минуту: https://hotheadsagency2019-debug.github.io/hhb-dashboard/"
fi

echo ""
echo "Нажми Enter чтобы закрыть..."
read
