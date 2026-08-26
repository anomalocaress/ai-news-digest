#!/usr/bin/env python3
"""
受信箱の課金メール監視 — 毎朝のワークフローの中で、新しい課金を勝手に見つける。

Gmail の App パスワード（GMAIL_APP_PASSWORD）は SMTP 送信だけでなく IMAP 読み取りにも
使えます。日次ダイジェストのメール配信で既に登録済みの Secret をそのまま流用するので、
新しい認証情報も、ブラウザ自動化も要りません。

読むのはヘッダ（From / Subject / Date）だけです。本文は取得しないので、
「請求書が来た」という事実だけを見て、中身は覗きません。
既読フラグも立てません（BODY.PEEK）。

使い方:
  python billing_watch.py                    # 直近2日ぶんを見る（毎朝の実行想定）
  python billing_watch.py --days 30          # 過去30日をまとめて棚卸し
  python billing_watch.py --days 7 --notify  # 見つかったらメールで知らせる

環境変数:
  GMAIL_ADDRESS / GMAIL_APP_PASSWORD  … 未設定なら何もせず正常終了する
"""

import argparse
import email
import email.header
import imaplib
import json
import os
import re
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, List, Optional

JST = timezone(timedelta(hours=9))
REPO_DIR = Path(__file__).parent
REPORT_FILE = REPO_DIR / ".billing-watch.json"

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993


def load_ledger() -> Dict:
    """実データがあればそれを、無ければひな形を読む（CI では後者になる）。"""
    for name in ("service_costs.json", "service_costs.sample.json"):
        p = REPO_DIR / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"⚠️  {name} の読み込みに失敗しました: {e}")
    return {"services": [], "mail": {}}


def decode_header(raw: Optional[str]) -> str:
    if not raw:
        return ""
    out = []
    for text, enc in email.header.decode_header(raw):
        if isinstance(text, bytes):
            try:
                out.append(text.decode(enc or "utf-8", errors="replace"))
            except LookupError:
                out.append(text.decode("utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out).strip()


def fetch_headers(days: int) -> List[Dict]:
    """直近 days 日ぶんのヘッダを取る。認証情報が無ければ空を返す。"""
    user = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")
    if not user or not password:
        print("ℹ️  GMAIL_ADDRESS / GMAIL_APP_PASSWORD が未設定のため受信箱は見ません")
        return []

    since = (datetime.now(JST) - timedelta(days=days)).strftime("%d-%b-%Y")
    messages: List[Dict] = []

    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    except Exception as e:
        print(f"⚠️  IMAP に接続できませんでした: {e}")
        return []

    try:
        conn.login(user, password)
        conn.select("INBOX", readonly=True)
        status, data = conn.search(None, f'(SINCE "{since}")')
        if status != "OK":
            print(f"⚠️  検索に失敗しました: {status}")
            return []

        ids = data[0].split()
        print(f"📬 直近{days}日で {len(ids)} 通を確認します")

        for msg_id in ids:
            status, raw = conn.fetch(
                msg_id, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])"
            )
            if status != "OK" or not raw or not isinstance(raw[0], tuple):
                continue
            msg = email.message_from_bytes(raw[0][1])
            messages.append({
                "from": decode_header(msg.get("From")),
                "subject": decode_header(msg.get("Subject")),
                "date": decode_header(msg.get("Date")),
            })
    except imaplib.IMAP4.error as e:
        # パスワードそのものは絶対にログへ出さない
        print(f"⚠️  Gmail にログインできませんでした（App パスワードを確認してください）: {type(e).__name__}")
        return []
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    return messages


def looks_like_billing(msg: Dict, signals: List[str]) -> bool:
    haystack = (msg["subject"] + " " + msg["from"]).lower()
    return any(sig.lower() in haystack for sig in signals)


def sender_ignored(msg: Dict, ignore: List[str]) -> bool:
    sender = msg["from"].lower()
    return any(pat.lower() in sender for pat in ignore)


def match_service(msg: Dict, services: List[Dict]) -> Optional[Dict]:
    haystack = (msg["from"] + " " + msg["subject"]).lower()
    for svc in services:
        for pat in svc.get("mail_match", []):
            if pat.lower() in haystack:
                return svc
    return None


def sender_domain(sender: str) -> str:
    m = re.search(r"@([\w.-]+)", sender)
    return m.group(1).lower() if m else sender.lower()


def scan(days: int) -> Dict:
    ledger = load_ledger()
    mail_cfg = ledger.get("mail", {})
    signals = mail_cfg.get("billing_signals", [])
    ignore = mail_cfg.get("ignore_senders", [])
    services = ledger.get("services", [])

    messages = fetch_headers(days)
    known: Dict[str, List[Dict]] = {}
    unknown: Dict[str, List[Dict]] = {}

    for msg in messages:
        if not looks_like_billing(msg, signals):
            continue
        if sender_ignored(msg, ignore):
            continue
        svc = match_service(msg, services)
        if svc:
            known.setdefault(svc["name"], []).append(msg)
        else:
            unknown.setdefault(sender_domain(msg["from"]), []).append(msg)

    # 台帳側の期限チェック（メールが来なくても効く）
    today = datetime.now(JST).date()
    deadlines = []
    for svc in services:
        if svc.get("status") in ("unused", "cancelled"):
            continue
        for key, label in (("trial_ends", "無料体験の終了"), ("next_charge", "次回請求")):
            raw = svc.get(key)
            if not raw:
                continue
            # 体験終了日と次回請求日が同じなら、意味が濃い「体験終了」だけ出す
            if key == "next_charge" and raw == svc.get("trial_ends"):
                continue
            try:
                d = datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                continue
            left = (d - today).days
            if 0 <= left <= 7:
                deadlines.append({"service": svc["name"], "what": label,
                                  "date": raw, "days_left": left})

    return {
        "scanned_at": datetime.now(JST).isoformat(timespec="seconds"),
        "days": days,
        "messages_checked": len(messages),
        "known": known,
        "unknown": unknown,
        "deadlines": sorted(deadlines, key=lambda x: x["days_left"]),
    }


def format_report(result: Dict) -> str:
    lines = []
    if result["unknown"]:
        lines.append("🔴 台帳に無い課金メールが届いています")
        for domain, msgs in result["unknown"].items():
            lines.append(f"  {domain}（{len(msgs)}通）")
            for m in msgs[:3]:
                lines.append(f"    ・{m['subject']}")
        lines.append("")
    if result["deadlines"]:
        lines.append("🟡 期限が近いもの")
        for d in result["deadlines"]:
            lines.append(f"  {d['service']}: {d['what']} まであと {d['days_left']} 日（{d['date']}）")
        lines.append("")
    if result["known"]:
        lines.append("● 既知のサービスからの請求")
        for name, msgs in result["known"].items():
            lines.append(f"  {name}（{len(msgs)}通）")
        lines.append("")
    if not lines:
        lines.append("✅ 新しい課金は見つかりませんでした")
    return "\n".join(lines)


def notify(result: Dict, body: str) -> bool:
    """新規の課金か期限が見つかったときだけ送る。"""
    user = os.getenv("GMAIL_ADDRESS")
    password = os.getenv("GMAIL_APP_PASSWORD")
    if not user or not password:
        return False

    subject = "【課金ウォッチ】"
    if result["unknown"]:
        subject += f"台帳に無い課金 {len(result['unknown'])} 件"
    elif result["deadlines"]:
        subject += f"期限が近いもの {len(result['deadlines'])} 件"
    else:
        return False

    msg = MIMEText(
        body + "\n\n台帳: https://claude.ai/code/artifact/2d12e881-53f5-492a-b8e8-0d6fdfbbcd46\n",
        "plain", "utf-8"
    )
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = "fujisaki@teraco-labo.com"

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(user, password)
            server.send_message(msg)
        print("📧 通知メールを送信しました")
        return True
    except smtplib.SMTPException as e:
        print(f"⚠️  通知メールを送れませんでした: {type(e).__name__}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="受信箱から新しい課金を見つける")
    ap.add_argument("--days", type=int, default=2, help="さかのぼる日数（既定 2）")
    ap.add_argument("--notify", action="store_true", help="見つかったらメールで知らせる")
    args = ap.parse_args()

    result = scan(args.days)
    report = format_report(result)
    print()
    print(report)

    try:
        REPORT_FILE.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as e:
        print(f"⚠️  記録の保存に失敗しました: {e}")

    if args.notify:
        notify(result, report)

    # 毎朝のワークフローを止めたくないので、見つかっても 0 で返す
    return 0


if __name__ == "__main__":
    sys.exit(main())
