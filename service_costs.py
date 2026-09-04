#!/usr/bin/env python3
"""
サブスクAPIチェッカー（台帳） — 「どこにいくら払っているか」を1枚で見る。

api_cost_calculator.py が扱うのは *このリポジトリのコードが呼んだ API* の従量課金だけです。
実際に財布から出ていくお金には、コードが一切関与しないもの（サブスク、前払いクレジット、
無料体験からの自動移行）が混ざります。fal のように「コードは呼んでいないのに請求が来る」
のはこの型です。そこを取りこぼさないための台帳が service_costs.json です。

使い方:
  python service_costs.py report            # 全サービスと月額合計
  python service_costs.py check             # 直近で危ないものだけ（cron向け・要対応なら exit 1）
  python service_costs.py add --id elevenlabs --name ElevenLabs --amount 5 --currency USD \
                              --category "AI API" --dashboard https://elevenlabs.io/app/subscription
"""

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

JST = timezone(timedelta(hours=9))
REPO_DIR = Path(__file__).parent
CONFIG_FILE = REPO_DIR / "service_costs.json"
SAMPLE_FILE = REPO_DIR / "service_costs.sample.json"

# 何日前から警告するか
TRIAL_WARN_DAYS = 14
CHARGE_WARN_DAYS = 7

STATUS_LABEL = {
    "active": "稼働中",
    "trial": "無料体験中",
    "watch": "要確認",
    "unused": "未使用",
    "cancelled": "解約済み",
}

CYCLE_LABEL = {"monthly": "毎月", "yearly": "毎年", "one_time": "都度"}

# 月額合計に数えるステータス
COUNTED = ("active", "trial", "watch")


def today_jst() -> date:
    return datetime.now(JST).date()


def load_config() -> Dict:
    # 実データは .gitignore 済み（公開リポジトリに金額を出さないため）。
    # 手元に無ければひな形から起こす。
    if not CONFIG_FILE.exists() and SAMPLE_FILE.exists():
        CONFIG_FILE.write_text(SAMPLE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
        print("📋 service_costs.sample.json から service_costs.json を作成しました。金額を埋めてください")

    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️  service_costs.json の読み込みに失敗しました: {e}")
    return {"jpy_per_usd": 150, "monthly_budget_jpy": 0, "services": []}


def save_config(cfg: Dict):
    CONFIG_FILE.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def to_jpy(amount: Optional[float], currency: str, rate: float) -> Optional[float]:
    if amount is None:
        return None
    return float(amount) * rate if currency.upper() == "USD" else float(amount)


def monthly_jpy(svc: Dict, rate: float) -> Optional[float]:
    """月あたりに均した円。一度きりの支払いは 0（合計を膨らませないため）。"""
    jpy = to_jpy(svc.get("amount"), svc.get("currency", "JPY"), rate)
    if jpy is None:
        return None
    cycle = svc.get("cycle", "monthly")
    if cycle == "yearly":
        return jpy / 12
    if cycle == "one_time":
        return 0.0
    return jpy


def parse_day(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def summarize(cfg: Dict = None) -> Dict:
    cfg = cfg or load_config()
    rate = float(cfg.get("jpy_per_usd", 150))
    rows: List[Dict] = []
    total = 0.0
    unknown = 0

    for svc in cfg.get("services", []):
        jpy = monthly_jpy(svc, rate)
        counted = svc.get("status") in COUNTED
        if counted:
            if jpy is None:
                unknown += 1
            else:
                total += jpy
        rows.append({**svc, "monthly_jpy": jpy, "counted": counted})

    rows.sort(key=lambda r: (r["monthly_jpy"] is None, -(r["monthly_jpy"] or 0)))
    return {
        "rate": rate,
        "rows": rows,
        "monthly_total_jpy": round(total),
        "unknown_count": unknown,
        "budget_jpy": cfg.get("monthly_budget_jpy", 0),
    }


def alerts(cfg: Dict = None, today: date = None) -> List[Dict]:
    """要対応のものを重い順に返す。level: danger / warn / info"""
    cfg = cfg or load_config()
    today = today or today_jst()
    rate = float(cfg.get("jpy_per_usd", 150))
    out: List[Dict] = []

    for svc in cfg.get("services", []):
        name = svc.get("name", svc.get("id", "?"))
        status = svc.get("status")
        if status in ("unused", "cancelled"):
            continue

        jpy = monthly_jpy(svc, rate)
        yen = f"{round(jpy):,}円/月" if jpy else "金額未確認"

        trial_end = parse_day(svc.get("trial_ends"))
        if status == "trial" and trial_end:
            left = (trial_end - today).days
            if left < 0:
                out.append({"level": "danger", "service": name,
                            "message": f"無料体験は {trial_end} に終了済み。{yen} の課金が始まっているはず"})
            elif left == 0:
                out.append({"level": "danger", "service": name,
                            "message": f"無料体験は今日（{trial_end}）が最終日。続けないなら今すぐ解約。放置すると {yen}"})
            elif left <= TRIAL_WARN_DAYS:
                out.append({"level": "danger", "service": name,
                            "message": f"無料体験があと {left} 日で終了（{trial_end}）。続けないなら前日までに解約。放置すると {yen}"})

        charge = parse_day(svc.get("next_charge"))
        if charge and status != "trial":
            left = (charge - today).days
            if 0 <= left <= CHARGE_WARN_DAYS:
                out.append({"level": "warn", "service": name,
                            "message": f"{left} 日後（{charge}）に次の請求。{yen}"})

        if svc.get("billing") == "prepaid":
            out.append({"level": "warn", "service": name,
                        "message": "前払いクレジット制。自動リチャージが ON だと残高が減るたび黙って再課金される。設定を確認"})

        if jpy is None and status in COUNTED:
            out.append({"level": "info", "service": name,
                        "message": "金額が未確認。請求書を見て service_costs.json の amount を埋める"})

    order = {"danger": 0, "warn": 1, "info": 2}
    out.sort(key=lambda a: order[a["level"]])
    return out


# ---------------------------------------------------------------- コマンド

def cmd_report(_args: List[str]):
    s = summarize()
    print("💳 サブスクAPIチェッカー — 課金しているサービス一覧\n")
    for r in s["rows"]:
        jpy = r["monthly_jpy"]
        amount = f"¥{round(jpy):>7,}" if jpy is not None else "   不明  "
        if not r["counted"]:
            amount = "     ―  "
        cycle = "都度" if r.get("cycle") == "one_time" else "/月"
        mark = {"active": "●", "trial": "◐", "watch": "○"}.get(r.get("status"), "×")
        print(f"  {mark} {amount}{cycle:<3}{r.get('name','?')}")
        print(f"        {r.get('category','')} / {STATUS_LABEL.get(r.get('status'), r.get('status'))}"
              f" / {r.get('dashboard') or 'ダッシュボードなし'}")
        if r.get("note"):
            print(f"        {r['note']}")
        print()

    print(f"  月額合計: ¥{s['monthly_total_jpy']:,}"
          + (f"（金額未確認 {s['unknown_count']} 件を除く）" if s["unknown_count"] else ""))
    budget = s["budget_jpy"]
    if budget:
        print(f"  予算（収益で賄いたい額）: ¥{budget:,} / 月  →  残り ¥{budget - s['monthly_total_jpy']:,}")

    a = alerts()
    if a:
        print("\n⚠️  要対応\n")
        for item in a:
            icon = {"danger": "🔴", "warn": "🟡", "info": "⚪"}[item["level"]]
            print(f"  {icon} {item['service']}: {item['message']}")


def cmd_check(_args: List[str]) -> int:
    a = alerts()
    if not a:
        print("✅ 直近で対応が必要な課金はありません")
        return 0
    for item in a:
        icon = {"danger": "🔴", "warn": "🟡", "info": "⚪"}[item["level"]]
        print(f"{icon} {item['service']}: {item['message']}")
    return 1 if any(i["level"] == "danger" for i in a) else 0


def cmd_add(args: List[str]) -> int:
    def opt(name, default=None):
        if f"--{name}" in args:
            return args[args.index(f"--{name}") + 1]
        return default

    svc_id = opt("id")
    if not svc_id:
        print("使い方: python service_costs.py add --id <ID> --name <名前> [--amount 10 --currency USD ...]")
        return 1

    cfg = load_config()
    if any(s.get("id") == svc_id for s in cfg["services"]):
        print(f"⚠️  {svc_id} はすでに登録されています")
        return 1

    amount = opt("amount")
    cfg["services"].append({
        "id": svc_id,
        "name": opt("name", svc_id),
        "category": opt("category", "AI API"),
        "billing": opt("billing", "usage"),
        "status": opt("status", "watch"),
        "amount": float(amount) if amount is not None else None,
        "currency": opt("currency", "JPY"),
        "cycle": opt("cycle", "monthly"),
        "next_charge": opt("next-charge"),
        "dashboard": opt("dashboard", ""),
        "note": opt("note", ""),
        "evidence": opt("evidence", ""),
    })
    save_config(cfg)
    print(f"✅ {svc_id} を service_costs.json に追加しました")
    return 0


# ---------------------------------------------------------------- ダッシュボード

def generate_service_costs_html() -> str:
    """dashboard_app.py に差し込むカード。api_dashboard.py から呼ばれる。"""
    s = summarize()
    a = alerts()

    html = '''<div class="card">
    <div class="card-title">💳 課金しているサービス</div>

    <div style="margin-bottom: 1.25rem; padding: 1.25rem; background: linear-gradient(135deg, #0f172a, #1e293b); border-radius: 8px; border-left: 4px solid #f472b6; text-align: center;">
      <div style="font-size: 2rem; font-weight: bold; color: #f472b6;">¥''' + f"{s['monthly_total_jpy']:,}" + '''</div>
      <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.4rem;">月額の固定費合計'''
    if s["unknown_count"]:
        html += f"（金額未確認 {s['unknown_count']} 件を除く）"
    html += '''</div>
    </div>'''

    if a:
        html += '''
    <div style="margin-bottom: 1.25rem; display: grid; gap: 0.5rem;">'''
        for item in a:
            color = {"danger": "#ef4444", "warn": "#f59e0b", "info": "#64748b"}[item["level"]]
            icon = {"danger": "🔴", "warn": "🟡", "info": "⚪"}[item["level"]]
            html += f'''
      <div style="padding: 0.75rem 1rem; background: #1e293b; border-left: 4px solid {color}; border-radius: 6px; font-size: 0.85rem; color: #e2e8f0;">
        {icon} <strong>{item["service"]}</strong> — {item["message"]}
      </div>'''
        html += '''
    </div>'''

    html += '''
    <div style="display: grid; gap: 0.75rem;">'''

    for r in s["rows"]:
        jpy = r["monthly_jpy"]
        if not r["counted"]:
            amount = "―"
        elif jpy is None:
            amount = "金額未確認"
        elif jpy == 0:
            amount = "¥0"
        else:
            amount = f"¥{round(jpy):,}"
        if r.get("cycle") == "one_time":
            spot = to_jpy(r.get("amount"), r.get("currency", "JPY"), s["rate"])
            amount = f"¥{round(spot):,}" if spot else "―"
        color = {"active": "#22c55e", "trial": "#f59e0b", "watch": "#60a5fa"}.get(r.get("status"), "#475569")
        url = r.get("dashboard") or "#"
        tag = "a" if url != "#" else "div"
        target = ' target="_blank"' if url != "#" else ""
        href = f' href="{url}"' if url != "#" else ""

        html += f'''
      <{tag}{href}{target} style="display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: 1rem; background: #1e293b; border: 1px solid #334155; border-left: 4px solid {color}; border-radius: 6px; text-decoration: none; color: #e2e8f0;">
        <div>
          <div style="font-weight: 600; font-size: 0.95rem;">{r.get("name", "?")}</div>
          <div style="font-size: 0.8rem; color: #94a3b8;">{r.get("category", "")} / {STATUS_LABEL.get(r.get("status"), "")}</div>
        </div>
        <div style="text-align: right; white-space: nowrap;">
          <div style="font-weight: 700; color: {color}; font-size: 1.05rem;">{amount}</div>
          <div style="font-size: 0.75rem; color: #64748b;">{CYCLE_LABEL.get(r.get("cycle"), r.get("cycle", ""))}</div>
        </div>
      </{tag}>'''

    html += '''
    </div>
  </div>'''
    return html


COMMANDS = {"report": cmd_report, "check": cmd_check, "add": cmd_add}


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else "report"
    if cmd not in COMMANDS:
        print(__doc__)
        return 1
    return COMMANDS[cmd](args[1:]) or 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # `| head` などで打ち切られたときに醜い traceback を出さない
        sys.exit(0)
