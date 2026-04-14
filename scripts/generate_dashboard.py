#!/usr/bin/env python3
"""
HHB Dashboard Generator
Дёргает Яндекс Директ API + Метрику по каждому аккаунту из accounts.json
и генерирует самодостаточный HTML-дашборд.

Использование:
    python generate_dashboard.py --days 30 --out ../docs/index.html
"""

import argparse
import json
import os
import sys
import datetime
import urllib.parse
import urllib.request
from pathlib import Path


# ──────────────────────────────────────────────
# Конфиг
# ──────────────────────────────────────────────

DIRECT_API_URL = "https://api.direct.yandex.com/json/v5"
METRICA_API_URL = "https://api-metrika.yandex.net/stat/v1/data"

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
ACCOUNTS_FILE = ROOT_DIR / "accounts.json"
TEMPLATE_FILE = ROOT_DIR / "templates" / "dashboard_template.html"
OUT_DIR = ROOT_DIR / "docs"


# ──────────────────────────────────────────────
# Яндекс Директ API
# ──────────────────────────────────────────────

def direct_request(token: str, login: str, service: str, method: str, params: dict) -> dict:
    url = f"{DIRECT_API_URL}/{service}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Login": login,
        "Content-Type": "application/json; charset=utf-8",
        "Accept-Language": "ru",
    }
    body = json.dumps({"method": method, "params": params}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[DIRECT ERROR] {service}.{method}: {e}", file=sys.stderr)
        return {}


def get_campaigns(token: str, login: str) -> list:
    resp = direct_request(token, login, "campaigns", "get", {
        "SelectionCriteria": {"States": ["ON", "SUSPENDED"]},
        "FieldNames": ["Id", "Name", "Type", "Statistics"],
    })
    return resp.get("result", {}).get("Campaigns", [])


def get_direct_stats(token: str, login: str, date_from: str, date_to: str) -> dict:
    campaigns = get_campaigns(token, login)
    totals = {"impressions": 0, "clicks": 0, "cost_rub": 0.0}
    campaign_summaries = {}

    for c in campaigns:
        stats = c.get("Statistics", {})
        impr = int(stats.get("Impressions", 0) or 0)
        clicks = int(stats.get("Clicks", 0) or 0)
        cost = float(stats.get("Cost", 0) or 0)

        totals["impressions"] += impr
        totals["clicks"] += clicks
        totals["cost_rub"] += cost

        ctr = round(clicks / impr * 100, 2) if impr > 0 else 0
        cpc = round(cost / clicks, 2) if clicks > 0 else 0

        cid = str(c["Id"])
        campaign_summaries[cid] = {
            "name": c.get("Name", ""),
            "shortName": c.get("Name", "")[:40],
            "subName": c.get("Type", ""),
            "type": "search" if "SEARCH" in c.get("Type", "") else "rsya",
            "current": {
                "impressions": impr,
                "clicks": clicks,
                "cost_rub": cost,
                "ctr": ctr,
                "cpc": cpc,
            },
            "prev": {"impressions": 0, "clicks": 0, "cost_rub": 0, "ctr": 0, "cpc": 0},
            "change": {"impressions_pct": 0, "clicks_pct": 0, "cost_pct": 0,
                       "ctr_pp": 0, "cpc_pct": 0},
        }

    totals["ctr"] = round(totals["clicks"] / totals["impressions"] * 100, 2) if totals["impressions"] > 0 else 0
    totals["cpc"] = round(totals["cost_rub"] / totals["clicks"], 2) if totals["clicks"] > 0 else 0

    return {"totals": totals, "campaign_summaries": campaign_summaries}


# ──────────────────────────────────────────────
# Яндекс Метрика API
# ──────────────────────────────────────────────

def metrica_request(token: str, counter_id: str, params: dict) -> dict:
    params["id"] = counter_id
    query = urllib.parse.urlencode(params)
    url = f"{METRICA_API_URL}?{query}"
    headers = {"Authorization": f"OAuth {token}"}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[METRICA ERROR] counter={counter_id}: {e}", file=sys.stderr)
        return {}


def get_metrica_daily(token: str, counter_id: str, date_from: str, date_to: str) -> dict:
    resp = metrica_request(token, counter_id, {
        "metrics": "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth,ym:s:avgVisitDurationSeconds",
        "dimensions": "ym:s:date",
        "date1": date_from,
        "date2": date_to,
        "sort": "ym:s:date",
        "limit": 100,
    })

    daily = []
    totals = {"visits": 0, "users": 0, "engaged": 0, "leads": 0,
              "bounce_rate": 0.0, "page_depth": 0.0, "avg_visit_duration_seconds": 0.0}

    data = resp.get("data", [])
    for row in data:
        dims = row.get("dimensions", [{}])
        metrics = row.get("metrics", [0, 0, 0, 0, 0])
        date = dims[0].get("name", "") if dims else ""
        visits = int(metrics[0]) if len(metrics) > 0 else 0
        users = int(metrics[1]) if len(metrics) > 1 else 0
        bounce_rate = float(metrics[2]) if len(metrics) > 2 else 0
        page_depth = float(metrics[3]) if len(metrics) > 3 else 0
        avg_dur = float(metrics[4]) if len(metrics) > 4 else 0
        engaged = int(visits * (1 - bounce_rate / 100))

        daily.append({
            "date": date,
            "visits": visits,
            "users": users,
            "bounce_rate": round(bounce_rate, 1),
            "page_depth": round(page_depth, 2),
            "avg_visit_duration_seconds": round(avg_dur, 0),
            "engaged": engaged,
            "leads": 0,
        })
        totals["visits"] += visits
        totals["users"] += users
        totals["engaged"] += engaged

    n = len(data)
    if n > 0:
        totals["bounce_rate"] = round(sum(r["bounce_rate"] for r in daily) / n, 1)
        totals["page_depth"] = round(sum(r["page_depth"] for r in daily) / n, 2)
        totals["avg_visit_duration_seconds"] = round(
            sum(r["avg_visit_duration_seconds"] for r in daily) / n, 0)

    return {"daily": daily, "totals": totals}


def get_metrica_goals(token: str, counter_id: str, date_from: str, date_to: str,
                      goal_ids: list) -> dict:
    if not goal_ids:
        return {"available": False, "goals": 0}

    metrics = ",".join(f"ym:s:goal{g}conversionRate,ym:s:goal{g}reaches" for g in goal_ids)
    resp = metrica_request(token, counter_id, {
        "metrics": metrics,
        "date1": date_from,
        "date2": date_to,
        "limit": 1,
    })
    totals_raw = resp.get("totals", [])
    goals = []
    total_leads = 0
    for i, gid in enumerate(goal_ids):
        conv_rate = totals_raw[i * 2] if len(totals_raw) > i * 2 else 0
        reaches = int(totals_raw[i * 2 + 1]) if len(totals_raw) > i * 2 + 1 else 0
        total_leads += reaches
        goals.append({"goal_id": gid, "reaches": reaches, "conv_rate": round(float(conv_rate), 2)})

    return {"available": True, "goals": len(goals), "total_leads": total_leads, "data": goals}


# ──────────────────────────────────────────────
# Сборка данных по аккаунту
# ──────────────────────────────────────────────

def pct_change(cur, prev):
    if not prev:
        return 0
    return round((cur - prev) / prev * 100, 1)


def build_account_data(token: str, account: dict, date_from: str, date_to: str,
                       prev_date_from: str, prev_date_to: str) -> dict:
    login = account["direct_client_login"]
    counter_ids = account.get("metrica_counter_ids", [])
    goal_ids = account.get("goal_ids", [])
    counter_id = counter_ids[0] if counter_ids else None

    print(f"  → Директ: {login} ({date_from} — {date_to})")
    direct_cur = get_direct_stats(token, login, date_from, date_to)
    print(f"  → Директ prev: {login} ({prev_date_from} — {prev_date_to})")
    direct_prev = get_direct_stats(token, login, prev_date_from, prev_date_to)

    metrica_current = {"daily": [], "totals": {"visits": 0, "users": 0, "engaged": 0, "leads": 0}}
    metrica_prev = {"daily": [], "totals": {"visits": 0, "users": 0, "engaged": 0, "leads": 0}}
    goals_data = {"available": False, "total_leads": 0}

    if counter_id:
        print(f"  → Метрика: счётчик {counter_id}")
        metrica_current = get_metrica_daily(token, counter_id, date_from, date_to)
        metrica_prev = get_metrica_daily(token, counter_id, prev_date_from, prev_date_to)

        if goal_ids:
            goals_data = get_metrica_goals(token, counter_id, date_from, date_to, goal_ids)
            total_leads = goals_data.get("total_leads", 0)
            metrica_current["totals"]["leads"] = total_leads
            # Распределяем лиды по дням равномерно
            n_days = len(metrica_current["daily"])
            if n_days > 0:
                per_day = total_leads // n_days
                for row in metrica_current["daily"]:
                    row["leads"] = per_day

    ct = direct_cur["totals"]
    pt = direct_prev["totals"]
    change = {
        "impressions_pct": pct_change(ct["impressions"], pt["impressions"]),
        "clicks_pct": pct_change(ct["clicks"], pt["clicks"]),
        "cost_pct": pct_change(ct["cost_rub"], pt["cost_rub"]),
        "ctr_pp": round(ct["ctr"] - pt["ctr"], 2),
        "cpc_pct": pct_change(ct["cpc"], pt["cpc"]),
    }

    return {
        "meta": {
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "date_from": date_from,
            "date_to": date_to,
            "prev_date_from": prev_date_from,
            "prev_date_to": prev_date_to,
            "account_id": account["id"],
            "project_name": account["name"],
            "direct_client_login": login,
            "counter_id": counter_id or "",
            "goal_ids": goal_ids,
        },
        "direct": {
            "current": {"daily": [], "totals": ct},
            "prev": {"daily": [], "totals": pt},
            "campaign_summaries": direct_cur["campaign_summaries"],
            "change": change,
        },
        "metrica": {
            "current": metrica_current,
            "prev": metrica_prev,
            "goals": goals_data,
        },
    }


# ──────────────────────────────────────────────
# Генерация HTML
# ──────────────────────────────────────────────

def generate_html(data: dict, template_path: Path) -> str:
    template = template_path.read_text(encoding="utf-8")
    json_data = json.dumps(data, ensure_ascii=False, indent=2)
    return template.replace("__DASHBOARD_DATA_PLACEHOLDER__", json_data)


# ──────────────────────────────────────────────
# Точка входа
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="HHB Dashboard Generator")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--out", type=str, default=str(OUT_DIR / "index.html"))
    parser.add_argument("--accounts", type=str, default=str(ACCOUNTS_FILE))
    parser.add_argument("--template", type=str, default=str(TEMPLATE_FILE))
    args = parser.parse_args()

    token = os.environ.get("YANDEX_TOKEN") or os.environ.get("YANDEX_ACCESS_TOKEN")
    if not token:
        print("ERROR: Установи переменную окружения YANDEX_TOKEN", file=sys.stderr)
        sys.exit(1)

    today = datetime.date.today() - datetime.timedelta(days=1)
    date_to = today.strftime("%Y-%m-%d")
    date_from = (today - datetime.timedelta(days=args.days - 1)).strftime("%Y-%m-%d")
    prev_date_to = (today - datetime.timedelta(days=args.days)).strftime("%Y-%m-%d")
    prev_date_from = (today - datetime.timedelta(days=args.days * 2 - 1)).strftime("%Y-%m-%d")

    print(f"Период: {date_from} — {date_to}")
    print(f"Сравнение: {prev_date_from} — {prev_date_to}")

    accounts_path = Path(args.accounts)
    config = json.loads(accounts_path.read_text(encoding="utf-8"))
    accounts = config["accounts"]
    print(f"Аккаунтов: {len(accounts)}")

    accounts_data = {}
    for acc in accounts:
        print(f"\n[{acc['id']}] {acc['name']}")
        try:
            accounts_data[acc["id"]] = build_account_data(
                token, acc, date_from, date_to, prev_date_from, prev_date_to
            )
        except Exception as e:
            print(f"  ✗ Ошибка: {e}", file=sys.stderr)
            accounts_data[acc["id"]] = {
                "error": str(e),
                "meta": {"project_name": acc["name"], "account_id": acc["id"]}
            }

    dashboard_data = {
        "meta": {
            "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
            "date_from": date_from,
            "date_to": date_to,
            "tool": "hhb-dashboard",
            "multi": len(accounts) > 1,
            "account_ids": [a["id"] for a in accounts],
            "default_account_id": accounts[0]["id"] if accounts else "",
        },
        "accounts": accounts_data,
    }

    template_path = Path(args.template)
    html = generate_html(dashboard_data, template_path)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    print(f"\n✓ Дашборд сохранён: {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
