#!/usr/bin/env python3
"""
HHB Dashboard Generator
Использует Яндекс Директ Reports API (TSV) + Метрику.
"""

import argparse
import json
import os
import sys
import datetime
import time
import urllib.parse
import urllib.request
from pathlib import Path

DIRECT_REPORTS_URL = "https://api.direct.yandex.com/json/v5/reports"
DIRECT_API_URL     = "https://api.direct.yandex.com/json/v5"
METRICA_API_URL    = "https://api-metrika.yandex.net/stat/v1/data"

SCRIPT_DIR    = Path(__file__).resolve().parent
ROOT_DIR      = SCRIPT_DIR.parent
ACCOUNTS_FILE = ROOT_DIR / "accounts.json"
TEMPLATE_FILE = ROOT_DIR / "templates" / "dashboard_template.html"
OUT_DIR       = ROOT_DIR / "docs"


# ─── Директ Reports API (TSV) ───────────────────────────────────────────────

def direct_report(token: str, login: str, params: dict, max_retries: int = 10) -> list[dict]:
    """
    Запрашивает отчёт через Reports API.
    Возвращает список dict (строки TSV без заголовка «Total»).
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Client-Login": login,
        "Accept-Language": "ru",
        "processingMode": "auto",
        "returnMoneyInMicros": "false",
        "skipReportHeader": "true",
        "skipColumnHeader": "false",
        "skipReportSummary": "true",
    }
    body = json.dumps({"params": params}).encode("utf-8")

    for attempt in range(max_retries):
        req = urllib.request.Request(DIRECT_REPORTS_URL, data=body, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                code = resp.getcode()
                raw = resp.read().decode("utf-8")
                if code == 200:
                    lines = raw.strip().split("\n")
                    if len(lines) < 2:
                        return []
                    cols = lines[0].split("\t")
                    rows = []
                    for line in lines[1:]:
                        parts = line.split("\t")
                        if len(parts) == len(cols):
                            rows.append(dict(zip(cols, parts)))
                    return rows
                # 201/202 — отчёт готовится, ждём
                retry_in = int(resp.headers.get("retryIn", 10))
                print(f"  [Reports] код {code}, ждём {retry_in}с...", file=sys.stderr)
                time.sleep(retry_in)
        except urllib.error.HTTPError as e:
            body_err = e.read().decode("utf-8", errors="ignore")
            if e.code in (201, 202):
                retry_in = int(e.headers.get("retryIn", 15))
                print(f"  [Reports] {e.code}, ждём {retry_in}с...", file=sys.stderr)
                time.sleep(retry_in)
            else:
                print(f"  [Reports ERROR] {e.code}: {body_err[:300]}", file=sys.stderr)
                return []
        except Exception as ex:
            print(f"  [Reports ERROR] {ex}", file=sys.stderr)
            return []

    print("  [Reports] превышено количество попыток", file=sys.stderr)
    return []


def get_direct_stats(token: str, login: str, date_from: str, date_to: str) -> dict:
    """
    Запрашивает статистику кампаний за период через Reports API.
    Возвращает totals + campaign_summaries + daily по кампаниям.
    """
    print(f"    Директ отчёт: {login} [{date_from} — {date_to}]")

    rows = direct_report(token, login, {
        "SelectionCriteria": {
            "DateFrom": date_from,
            "DateTo":   date_to,
        },
        "FieldNames": [
            "Date", "CampaignId", "CampaignName", "CampaignType",
            "Impressions", "Clicks", "Cost", "Ctr", "AvgCpc",
        ],
        "ReportName":    f"hhb_{login}_{date_from}_{date_to}",
        "ReportType":    "CAMPAIGN_PERFORMANCE_REPORT",
        "DateRangeType": "CUSTOM_DATE",
        "Format":        "TSV",
        "IncludeVAT":    "NO",
        "IncludeDiscount": "NO",
    })

    totals = {"impressions": 0, "clicks": 0, "cost_rub": 0.0, "ctr": 0.0, "cpc": 0.0}
    # campaign_id -> {meta, daily: [{date,impressions,clicks,cost_rub}], totals}
    camp_map: dict[str, dict] = {}

    for r in rows:
        cid   = r.get("CampaignId", "")
        cname = r.get("CampaignName", "")
        ctype = r.get("CampaignType", "")
        date  = r.get("Date", "")
        impr  = int(r.get("Impressions", 0) or 0)
        clicks= int(r.get("Clicks", 0) or 0)
        cost  = float(r.get("Cost", 0) or 0)

        totals["impressions"] += impr
        totals["clicks"]      += clicks
        totals["cost_rub"]    += cost

        if cid not in camp_map:
            camp_map[cid] = {
                "name":      cname,
                "shortName": cname[:45],
                "type":      "search" if "SEARCH" in ctype else ("rsya" if "NETWORK" in ctype else "other"),
                "rawType":   ctype,
                "daily":     [],
                "totals":    {"impressions":0,"clicks":0,"cost_rub":0.0},
            }
        camp_map[cid]["daily"].append({"date":date,"impressions":impr,"clicks":clicks,"cost_rub":cost})
        camp_map[cid]["totals"]["impressions"] += impr
        camp_map[cid]["totals"]["clicks"]      += clicks
        camp_map[cid]["totals"]["cost_rub"]    += cost

    # Финальные totals
    if totals["impressions"] > 0:
        totals["ctr"] = round(totals["clicks"] / totals["impressions"] * 100, 2)
    if totals["clicks"] > 0:
        totals["cpc"] = round(totals["cost_rub"] / totals["clicks"], 2)

    # campaign_summaries
    campaign_summaries = {}
    for cid, c in camp_map.items():
        ct   = c["totals"]
        impr = ct["impressions"]
        clk  = ct["clicks"]
        cst  = ct["cost_rub"]
        campaign_summaries[cid] = {
            "name":      c["name"],
            "shortName": c["shortName"],
            "type":      c["type"],
            "rawType":   c["rawType"],
            "daily":     c["daily"],
            "current": {
                "impressions": impr,
                "clicks":      clk,
                "cost_rub":    round(cst, 2),
                "ctr":         round(clk / impr * 100, 2) if impr > 0 else 0,
                "cpc":         round(cst / clk, 2) if clk > 0 else 0,
            },
            "prev":   {"impressions":0,"clicks":0,"cost_rub":0,"ctr":0,"cpc":0},
            "change": {"impressions_pct":0,"clicks_pct":0,"cost_pct":0,"ctr_pp":0,"cpc_pct":0},
        }

    return {"totals": totals, "campaign_summaries": campaign_summaries}


# ─── Метрика ─────────────────────────────────────────────────────────────────

def metrica_req(token: str, counter_id: str, params: dict) -> dict:
    params["id"] = counter_id
    url = f"{METRICA_API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"OAuth {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [Metrica ERROR] counter={counter_id}: {e}", file=sys.stderr)
        return {}


def get_metrica_daily(token: str, counter_id: str, date_from: str, date_to: str) -> dict:
    resp = metrica_req(token, counter_id, {
        "metrics":    "ym:s:visits,ym:s:users,ym:s:bounceRate,ym:s:pageDepth,ym:s:avgVisitDurationSeconds",
        "dimensions": "ym:s:date",
        "date1": date_from, "date2": date_to,
        "sort": "ym:s:date", "limit": 100,
    })
    daily  = []
    totals = {"visits":0,"users":0,"engaged":0,"leads":0,
              "bounce_rate":0.0,"page_depth":0.0,"avg_visit_duration_seconds":0.0}

    for row in resp.get("data", []):
        dims    = row.get("dimensions", [{}])
        metrics = row.get("metrics", [0]*5)
        date    = dims[0].get("name","") if dims else ""
        visits  = int(metrics[0]) if len(metrics)>0 else 0
        users   = int(metrics[1]) if len(metrics)>1 else 0
        br      = float(metrics[2]) if len(metrics)>2 else 0
        pd_     = float(metrics[3]) if len(metrics)>3 else 0
        dur     = float(metrics[4]) if len(metrics)>4 else 0
        engaged = int(visits * (1 - br/100))
        daily.append({"date":date,"visits":visits,"users":users,
                      "bounce_rate":round(br,1),"page_depth":round(pd_,2),
                      "avg_visit_duration_seconds":round(dur,0),"engaged":engaged,"leads":0})
        totals["visits"]  += visits
        totals["users"]   += users
        totals["engaged"] += engaged

    n = len(daily)
    if n > 0:
        totals["bounce_rate"] = round(sum(r["bounce_rate"] for r in daily)/n, 1)
        totals["page_depth"]  = round(sum(r["page_depth"]  for r in daily)/n, 2)
        totals["avg_visit_duration_seconds"] = round(
            sum(r["avg_visit_duration_seconds"] for r in daily)/n, 0)
    return {"daily": daily, "totals": totals}


def get_metrica_goals(token: str, counter_id: str, date_from: str, date_to: str,
                      goal_ids: list) -> dict:
    if not goal_ids:
        return {"available": False, "total_leads": 0}
    metrics = ",".join(f"ym:s:goal{g}reaches" for g in goal_ids)
    resp = metrica_req(token, counter_id, {
        "metrics": metrics, "date1": date_from, "date2": date_to, "limit": 1,
    })
    raw   = resp.get("totals", [])
    goals = []
    total = 0
    for i, gid in enumerate(goal_ids):
        reaches = int(raw[i]) if i < len(raw) else 0
        total  += reaches
        goals.append({"goal_id": gid, "reaches": reaches})
    return {"available": True, "total_leads": total, "data": goals}


# ─── Сборка аккаунта ─────────────────────────────────────────────────────────

def pct(cur, prev):
    return round((cur - prev) / prev * 100, 1) if prev else 0


def build_account(token: str, account: dict,
                  date_from: str, date_to: str,
                  prev_from: str, prev_to: str) -> dict:
    login      = account["direct_client_login"]
    counter_id = (account.get("metrica_counter_ids") or [None])[0]
    goal_ids   = account.get("goal_ids", [])

    cur_direct  = get_direct_stats(token, login, date_from, date_to)
    prev_direct = get_direct_stats(token, login, prev_from, prev_to)

    # Обогащаем campaign_summaries данными prev + change
    for cid, c in cur_direct["campaign_summaries"].items():
        pc = prev_direct["campaign_summaries"].get(cid, {})
        p  = pc.get("current", {"impressions":0,"clicks":0,"cost_rub":0,"ctr":0,"cpc":0})
        cr = c["current"]
        c["prev"]   = p
        c["change"] = {
            "impressions_pct": pct(cr["impressions"], p["impressions"]),
            "clicks_pct":      pct(cr["clicks"],      p["clicks"]),
            "cost_pct":        pct(cr["cost_rub"],    p["cost_rub"]),
            "ctr_pp":          round(cr["ctr"] - p["ctr"], 2),
            "cpc_pct":         pct(cr["cpc"],          p["cpc"]),
        }

    # Totals change
    ct = cur_direct["totals"]
    pt = prev_direct["totals"]
    totals_change = {
        "impressions_pct": pct(ct["impressions"], pt["impressions"]),
        "clicks_pct":      pct(ct["clicks"],      pt["clicks"]),
        "cost_pct":        pct(ct["cost_rub"],    pt["cost_rub"]),
        "ctr_pp":          round(ct["ctr"] - pt["ctr"], 2),
        "cpc_pct":         pct(ct["cpc"],          pt["cpc"]),
    }

    # Метрика
    met_cur  = {"daily":[], "totals":{"visits":0,"users":0,"engaged":0,"leads":0}}
    met_prev = {"daily":[], "totals":{"visits":0,"users":0,"engaged":0,"leads":0}}
    goals    = {"available": False, "total_leads": 0}

    if counter_id:
        print(f"    Метрика счётчик {counter_id}")
        met_cur  = get_metrica_daily(token, counter_id, date_from, date_to)
        met_prev = get_metrica_daily(token, counter_id, prev_from,  prev_to)
        if goal_ids:
            goals = get_metrica_goals(token, counter_id, date_from, date_to, goal_ids)
            leads = goals["total_leads"]
            met_cur["totals"]["leads"] = leads
            n = len(met_cur["daily"])
            if n > 0:
                for row in met_cur["daily"]:
                    row["leads"] = leads // n

    return {
        "meta": {
            "generated_at":        datetime.datetime.utcnow().isoformat() + "Z",
            "date_from":           date_from,
            "date_to":             date_to,
            "prev_date_from":      prev_from,
            "prev_date_to":        prev_to,
            "account_id":          account["id"],
            "project_name":        account["name"],
            "direct_client_login": login,
            "counter_id":          counter_id or "",
            "goal_ids":            goal_ids,
        },
        "direct": {
            "current":            {"totals": ct},
            "prev":               {"totals": pt},
            "change":             totals_change,
            "campaign_summaries": cur_direct["campaign_summaries"],
        },
        "metrica": {
            "current": met_cur,
            "prev":    met_prev,
            "goals":   goals,
        },
    }


# ─── HTML ────────────────────────────────────────────────────────────────────

def generate_html(data: dict, template: Path) -> str:
    tpl = template.read_text(encoding="utf-8")
    return tpl.replace("__DASHBOARD_DATA_PLACEHOLDER__",
                       json.dumps(data, ensure_ascii=False, indent=2))


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days",      type=int, default=30)
    p.add_argument("--out",       default=str(OUT_DIR / "index.html"))
    p.add_argument("--accounts",  default=str(ACCOUNTS_FILE))
    p.add_argument("--template",  default=str(TEMPLATE_FILE))
    args = p.parse_args()

    token = os.environ.get("YANDEX_TOKEN") or os.environ.get("YANDEX_ACCESS_TOKEN")
    if not token:
        print("ERROR: нет YANDEX_TOKEN", file=sys.stderr); sys.exit(1)

    today     = datetime.date.today() - datetime.timedelta(days=1)
    date_to   = today.strftime("%Y-%m-%d")
    date_from = (today - datetime.timedelta(days=args.days-1)).strftime("%Y-%m-%d")
    prev_to   = (today - datetime.timedelta(days=args.days)).strftime("%Y-%m-%d")
    prev_from = (today - datetime.timedelta(days=args.days*2-1)).strftime("%Y-%m-%d")

    print(f"Период:    {date_from} — {date_to}")
    print(f"Сравнение: {prev_from} — {prev_to}")

    config   = json.loads(Path(args.accounts).read_text(encoding="utf-8"))
    accounts = config["accounts"]
    print(f"Аккаунтов: {len(accounts)}\n")

    acc_data = {}
    for acc in accounts:
        print(f"[{acc['id']}] {acc['name']}")
        try:
            acc_data[acc["id"]] = build_account(
                token, acc, date_from, date_to, prev_from, prev_to)
            print(f"  ✓ готово")
        except Exception as e:
            print(f"  ✗ ошибка: {e}", file=sys.stderr)
            acc_data[acc["id"]] = {
                "error": str(e),
                "meta": {"project_name": acc["name"], "account_id": acc["id"]},
            }

    dashboard = {
        "meta": {
            "generated_at":     datetime.datetime.utcnow().isoformat() + "Z",
            "date_from":        date_from,
            "date_to":          date_to,
            "tool":             "hhb-dashboard",
            "multi":            len(accounts) > 1,
            "account_ids":      [a["id"] for a in accounts],
            "default_account_id": accounts[0]["id"] if accounts else "",
        },
        "accounts": acc_data,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(generate_html(dashboard, Path(args.template)), encoding="utf-8")
    print(f"\n✓ {out}  ({out.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
