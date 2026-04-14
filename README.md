# HHB Dashboard

Автоматически обновляемый дашборд Яндекс Директ + Метрика, публикуемый на GitHub Pages.

**Живой дашборд:** `https://<твой-логин>.github.io/<имя-репозитория>/`

---

## Структура проекта

```
hhb-dashboard/
├── accounts.json                        ← реестр аккаунтов (редактируешь сам)
├── scripts/
│   └── generate_dashboard.py            ← скрипт генерации HTML
├── templates/
│   └── dashboard_template.html          ← HTML-шаблон дашборда
├── docs/
│   └── index.html                       ← сгенерированный дашборд (не редактировать)
└── .github/
    └── workflows/
        └── update-dashboard.yml         ← GitHub Actions (запуск каждый день в 09:00 МСК)
```

---

## Настройка аккаунтов

Открой [accounts.json](accounts.json) и заполни свои данные:

```json
{
  "direct_login": "hotheads-marketing",
  "accounts": [
    {
      "id": "client_slug",
      "name": "Название клиента",
      "direct_client_login": "логин-в-директе",
      "metrica_counter_ids": ["12345678"],
      "goal_ids": ["123", "456"]
    }
  ]
}
```

| Поле | Описание |
|------|----------|
| `id` | Уникальный slug аккаунта (латиница, без пробелов) |
| `name` | Название — показывается в дашборде |
| `direct_client_login` | Логин клиента в Яндекс Директе |
| `metrica_counter_ids` | Массив ID счётчиков Метрики |
| `goal_ids` | ID целей Метрики для воронки (пустой массив = без целей) |

---

## Подключение GitHub Pages (делается один раз)

### 1. Создать репозиторий на GitHub

```bash
# Из папки hhb-dashboard
git init
git add .
git commit -m "init: hhb-dashboard"
gh repo create hhb-dashboard --public --push --source=.
```

### 2. Добавить секрет YANDEX_TOKEN

1. Открыть репозиторий на GitHub
2. Settings → Secrets and variables → Actions → New repository secret
3. Name: `YANDEX_TOKEN`
4. Value: твой OAuth-токен Яндекса

### 3. Включить GitHub Pages

1. Settings → Pages
2. Source: **Deploy from a branch**
3. Branch: **gh-pages** / (root)
4. Save

### 4. Запустить первую генерацию

1. Actions → Update HHB Dashboard → Run workflow
2. Через ~1 минуту дашборд появится по адресу `https://<login>.github.io/hhb-dashboard/`

---

## Расписание обновлений

Дашборд обновляется **автоматически каждый день в 09:00 МСК** (06:00 UTC).

Для ручного запуска: Actions → Update HHB Dashboard → Run workflow.

---

## Локальный запуск (тест)

```bash
export YANDEX_TOKEN="ваш_токен"
python scripts/generate_dashboard.py --days 30
# Откроет docs/index.html
open docs/index.html
```
