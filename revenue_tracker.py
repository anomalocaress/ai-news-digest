#!/usr/bin/env python3
"""
収支トラッカー — 「Claude Code の月額を自動で賄う」という目的に対して、
いま何%まで到達しているかを数字で見る。

収益データは revenue.json に貯めます。このファイルは .gitignore 済みで、
公開リポジトリには push されません（収益額は公開したくない情報のため）。

使い方:
  python revenue_tracker.py add --amount 8000 --source a8 --offer conoha-wing
  python revenue_tracker.py report              # 今月の収支
  python revenue_tracker.py report --month 2026-08
  python revenue_tracker.py plan                # 目標達成に必要な成約件数の逆算
  python revenue_tracker.py target --amount 30000
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List

import monetize

JST = timezone(timedelta(hours=9))
REPO_DIR = Path(__file__).parent
DATA_FILE = REPO_DIR / "revenue.json"
REPORT_FILE = REPO_DIR / ".revenue-report.html"

DEFAULT_TARGET_JPY = 30000  # Claude Code Max プラン相当


def load_data() -> Dict:
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠️  revenue.json の読み込みに失敗しました: {e}")
    return {"target_monthly_jpy": DEFAULT_TARGET_JPY, "entries": []}


def save_data(data: Dict):
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def api_cost_jpy() -> float:
    """記録済みのAPI利用料（円）。取得できなければ 0。"""
    try:
        import api_cost_calculator
        return float(api_cost_calculator.get_current_costs().get("total_jpy", 0))
    except Exception:
        return 0.0


# ---------------------------------------------------------------- コマンド

def cmd_add(args: List[str]):
    def opt(name, default=None):
        return args[args.index(name) + 1] if name in args else default

    amount = opt("--amount")
    if amount is None:
        print("エラー: --amount は必須です（例: --amount 8000）")
        return

    data = load_data()
    entry = {
        "date": opt("--date", datetime.now(JST).strftime("%Y-%m-%d")),
        "amount_jpy": int(float(amount)),
        "source": opt("--source", "unknown"),
        "offer": opt("--offer", ""),
        "note": opt("--note", ""),
    }
    data.setdefault("entries", []).append(entry)
    data["entries"].sort(key=lambda e: e["date"])
    save_data(data)
    print(f"✓ 記録しました: {entry['date']} {entry['amount_jpy']:,}円 "
          f"({entry['source']}{' / ' + entry['offer'] if entry['offer'] else ''})")

    month = entry["date"][:7]
    total = sum(e["amount_jpy"] for e in data["entries"] if e["date"].startswith(month))
    target = data.get("target_monthly_jpy", DEFAULT_TARGET_JPY)
    print(f"  {month} の累計: {total:,}円 / {target:,}円 ({total / target * 100:.1f}%)")


def cmd_target(args: List[str]):
    if "--amount" not in args:
        print("エラー: --amount は必須です（例: --amount 30000）")
        return
    data = load_data()
    data["target_monthly_jpy"] = int(float(args[args.index("--amount") + 1]))
    save_data(data)
    print(f"✓ 月間目標を {data['target_monthly_jpy']:,}円 に設定しました")


def _bar(ratio: float, width: int = 30) -> str:
    filled = min(int(ratio * width), width)
    return "█" * filled + "░" * (width - filled)


def cmd_report(args: List[str]):
    data = load_data()
    target = data.get("target_monthly_jpy", DEFAULT_TARGET_JPY)
    month = args[args.index("--month") + 1] if "--month" in args else datetime.now(JST).strftime("%Y-%m")

    entries = [e for e in data.get("entries", []) if e["date"].startswith(month)]
    total = sum(e["amount_jpy"] for e in entries)
    cost = api_cost_jpy()

    print(f"\n💰 収支レポート {month}")
    print("=" * 52)
    print(f"  目標          {target:>10,} 円/月")
    print(f"  収益          {total:>10,} 円")
    print(f"  API実費(累計) {cost:>10,.0f} 円")
    print(f"  差引          {total - cost:>10,.0f} 円")
    print()
    ratio = total / target if target else 0
    print(f"  達成率 {ratio * 100:5.1f}%  [{_bar(ratio)}]")
    print(f"  残り   {max(target - total, 0):,} 円")
    print("=" * 52)

    if entries:
        print("\n  内訳:")
        by_source: Dict[str, int] = {}
        for e in entries:
            by_source[e["source"]] = by_source.get(e["source"], 0) + e["amount_jpy"]
        for source, amount in sorted(by_source.items(), key=lambda x: -x[1]):
            print(f"    {source:<16} {amount:>8,} 円")
        print("\n  明細:")
        for e in entries:
            label = f"{e['source']}/{e['offer']}" if e["offer"] else e["source"]
            print(f"    {e['date']}  {e['amount_jpy']:>7,}円  {label}"
                  + (f"  {e['note']}" if e["note"] else ""))
    else:
        print(f"\n  {month} の記録はまだありません。")
        print("  成果が出たら: python revenue_tracker.py add --amount 8000 --source a8")

    _write_html_report(month, entries, total, target, cost)
    print(f"\n  HTMLレポート: {REPORT_FILE.name}（ローカルのみ・push されません）\n")


def cmd_plan(args: List[str]):
    """目標額に到達するために、どの案件が何件必要かを逆算する。"""
    data = load_data()
    target = data.get("target_monthly_jpy", DEFAULT_TARGET_JPY)
    config = monetize.load_config()
    offers = config.get("offers", [])

    print(f"\n🎯 月 {target:,}円 に到達するための逆算")
    print("=" * 72)
    print(f"  {'案件':<22}{'想定単価':>10}{'必要件数':>10}{'必要クリック':>12}{'必要PV':>10}")
    print("-" * 72)

    # 業界の一般的な水準を仮置き（実測が貯まったら差し替える）
    ASSUMED_CVR = 0.01   # クリック→成約
    ASSUMED_CTR = 0.03   # PV→クリック

    for o in sorted(offers, key=lambda x: -x.get("payout_jpy_est", 0)):
        payout = o.get("payout_jpy_est", 0)
        if payout <= 0:
            continue
        need = target / payout
        clicks = need / ASSUMED_CVR
        pv = clicks / ASSUMED_CTR
        live = "✓" if monetize._filled(o.get("url")) else " "
        print(f"{live} {o['name']:<20}{payout:>9,}円{need:>9.1f}件{clicks:>11,.0f}{pv:>10,.0f}")

    print("=" * 72)
    print(f"  前提: 成約率 {ASSUMED_CVR:.0%} / クリック率 {ASSUMED_CTR:.0%}")
    print("  ✓ = アフィリエイトURL設定済み（実際に掲出されている案件）")
    print("\n  読み方: 単価が高い案件ほど必要PVが少なくて済みます。")
    print("  1万円級の案件なら月1万PVが目安。1万PVは解説記事20本×各500PVのレンジです。\n")


def _write_html_report(month: str, entries: List[Dict], total: int, target: int, cost: float):
    ratio = min(total / target, 1.0) if target else 0
    rows = "".join(
        f"<tr><td>{e['date']}</td><td>{e['source']}</td><td>{e.get('offer', '')}</td>"
        f"<td style='text-align:right'>{e['amount_jpy']:,}</td><td>{e.get('note', '')}</td></tr>"
        for e in entries
    ) or "<tr><td colspan='5' style='text-align:center;color:#94a3b8'>記録なし</td></tr>"

    REPORT_FILE.write_text(f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>収支レポート {month}</title>
<style>
 body{{font-family:'Noto Sans JP',sans-serif;background:#0f172a;color:#e2e8f0;padding:2rem;line-height:1.7}}
 .wrap{{max-width:760px;margin:0 auto}}
 h1{{font-size:1.3rem;margin-bottom:1.5rem}}
 .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1rem;margin-bottom:1.5rem}}
 .card{{background:#1e293b;padding:1.2rem;border-radius:8px}}
 .card .l{{font-size:.72rem;color:#94a3b8}}
 .card .v{{font-size:1.5rem;font-weight:700;margin-top:.3rem}}
 .bar{{height:14px;background:#1e293b;border-radius:7px;overflow:hidden;margin:.5rem 0 1.5rem}}
 .bar>div{{height:100%;background:linear-gradient(90deg,#22d3ee,#0e7490);width:{ratio*100:.1f}%}}
 table{{width:100%;border-collapse:collapse;font-size:.85rem}}
 th,td{{padding:.5rem .7rem;border-bottom:1px solid #334155;text-align:left}}
 th{{color:#94a3b8;font-size:.75rem}}
</style></head><body><div class="wrap">
<h1>収支レポート — {month}</h1>
<div class="cards">
  <div class="card"><div class="l">今月の収益</div><div class="v">{total:,}<span style="font-size:.8rem">円</span></div></div>
  <div class="card"><div class="l">月間目標</div><div class="v">{target:,}<span style="font-size:.8rem">円</span></div></div>
  <div class="card"><div class="l">達成率</div><div class="v">{(total/target*100 if target else 0):.1f}<span style="font-size:.8rem">%</span></div></div>
  <div class="card"><div class="l">API実費(累計)</div><div class="v">{cost:,.0f}<span style="font-size:.8rem">円</span></div></div>
</div>
<div class="bar"><div></div></div>
<table><thead><tr><th>日付</th><th>ASP</th><th>案件</th><th style="text-align:right">金額</th><th>メモ</th></tr></thead>
<tbody>{rows}</tbody></table>
</div></body></html>
""", encoding="utf-8")


def main():
    args = sys.argv[1:]
    command = args[0] if args else "report"
    handlers = {"add": cmd_add, "report": cmd_report, "plan": cmd_plan, "target": cmd_target}
    handler = handlers.get(command)
    if not handler:
        print(__doc__)
        return
    handler(args[1:])


if __name__ == "__main__":
    main()
