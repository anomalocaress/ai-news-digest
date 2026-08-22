#!/usr/bin/env python3
"""朝のブリーフィング生成

Chatwork から Mキャリ（AI×動画編集講師）関連のタスク・メンションを取得し、
HTML ブリーフィングをメールで届ける。

必要な環境変数:
  CHATWORK_API_TOKEN   Chatwork API トークン（必須）
  GMAIL_ADDRESS        送信元 Gmail アドレス（メール送信時）
  GMAIL_APP_PASSWORD   Gmail アプリパスワード（メール送信時）

任意の環境変数:
  CHATWORK_MCAREER_KEYWORD    Mキャリ関連ルームをルーム名で判定するキーワード
                              （カンマ区切り可。デフォルト: "Mキャリ,エムキャリ"）
  CHATWORK_MCAREER_ROOM_IDS   Mキャリ関連ルームのルームIDをカンマ区切りで明示指定
                              （指定するとキーワード判定より優先される）
  BRIEFING_EMAIL_TO           送信先（デフォルト: fujisaki@teraco-labo.com）
"""

import os
import re
import sys
import html
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional

import requests

# Load environment variables (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# JST = UTC+9（generate_news.py と同じ理由で JST 基準で「今日」を判定する）
JST = timezone(timedelta(hours=9))
WEEKDAYS_JA = ["月", "火", "水", "木", "金", "土", "日"]

REPO_DIR = Path(__file__).parent
CHATWORK_API_BASE = "https://api.chatwork.com/v2"

DEFAULT_EMAIL_TO = "fujisaki@teraco-labo.com"
DEFAULT_MCAREER_KEYWORDS = ["Mキャリ", "エムキャリ"]

# 直近のやりとりとして拾う時間幅
RECENT_HOURS = 24


# ---------------------------------------------------------------------------
# Chatwork API
# ---------------------------------------------------------------------------

class ChatworkClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers["X-ChatWorkToken"] = token

    def _get(self, path: str, params: Optional[dict] = None):
        url = f"{CHATWORK_API_BASE}{path}"
        resp = self.session.get(url, params=params, timeout=15)
        if resp.status_code == 204:
            # Chatwork は該当データなしのとき 204 No Content を返す
            return None
        resp.raise_for_status()
        return resp.json()

    def me(self) -> dict:
        return self._get("/me") or {}

    def rooms(self) -> List[dict]:
        return self._get("/rooms") or []

    def my_open_tasks(self) -> List[dict]:
        return self._get("/my/tasks", params={"status": "open"}) or []

    def recent_messages(self, room_id: int) -> List[dict]:
        """最新最大100件を取得（force=1 で未読既読に関わらず取得）"""
        return self._get(f"/rooms/{room_id}/messages", params={"force": 1}) or []


CHATWORK_TAG_PATTERNS = [
    re.compile(r"\[/?qt\]|\[qtmeta[^\]]*\]"),
    re.compile(r"\[To:\d+\]"),
    re.compile(r"\[rp aid=\d+[^\]]*\]"),
    re.compile(r"\[piconname:\d+\]|\[picon:\d+\]"),
    re.compile(r"\[/?(info|title|code|hr)\]"),
    re.compile(r"\[dtext:[^\]]+\]"),
    re.compile(r"\[preview[^\]]*\]"),
    re.compile(r"\[download[^\]]*\].*?\[/download\]", re.DOTALL),
]


def clean_chatwork_body(body: str) -> str:
    """Chatwork 独自タグを除去して読みやすいテキストにする"""
    text = body
    for pat in CHATWORK_TAG_PATTERNS:
        text = pat.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def truncate(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------------------
# データ収集
# ---------------------------------------------------------------------------

def mcareer_room_matcher():
    """環境変数から Mキャリ関連ルームの判定関数を作る"""
    room_ids_env = os.getenv("CHATWORK_MCAREER_ROOM_IDS", "").strip()
    if room_ids_env:
        ids = {int(x) for x in re.split(r"[,\s]+", room_ids_env) if x.strip().isdigit()}
        return lambda room_id, room_name: room_id in ids

    keywords_env = os.getenv("CHATWORK_MCAREER_KEYWORD", "").strip()
    keywords = (
        [k.strip() for k in keywords_env.split(",") if k.strip()]
        if keywords_env
        else DEFAULT_MCAREER_KEYWORDS
    )
    return lambda room_id, room_name: any(k.lower() in (room_name or "").lower() for k in keywords)


def classify_due(limit_time: int, now: datetime) -> Dict:
    """期限の unix 時刻から表示ラベルと緊急度を決める"""
    if not limit_time:
        return {"label": "期限なし", "urgency": 3}
    due = datetime.fromtimestamp(limit_time, tz=JST)
    today = now.astimezone(JST).date()
    if due.date() < today:
        return {"label": f"期限切れ（{due.strftime('%m/%d')}）", "urgency": 0}
    if due.date() == today:
        return {"label": "今日まで", "urgency": 1}
    days = (due.date() - today).days
    label = f"{due.strftime('%m/%d')}（{WEEKDAYS_JA[due.weekday()]}）"
    return {"label": label, "urgency": 2 if days <= 3 else 3}


def gather_briefing_data(client: ChatworkClient, now: datetime) -> Dict:
    """Chatwork からブリーフィングに必要なデータを集める"""
    me = client.me()
    my_account_id = me.get("account_id")

    is_mcareer = mcareer_room_matcher()

    # --- 自分のオープンタスク（全ルーム横断） ---
    tasks = client.my_open_tasks()
    mcareer_tasks: List[Dict] = []
    other_tasks: List[Dict] = []
    for t in tasks:
        room = t.get("room") or {}
        item = {
            "room_name": room.get("name", ""),
            "body": clean_chatwork_body(t.get("body", "")),
            "assigned_by": (t.get("assigned_by_account") or {}).get("name", ""),
            **classify_due(t.get("limit_time") or 0, now),
        }
        if is_mcareer(room.get("room_id"), room.get("name")):
            mcareer_tasks.append(item)
        else:
            other_tasks.append(item)
    mcareer_tasks.sort(key=lambda x: x["urgency"])
    other_tasks.sort(key=lambda x: x["urgency"])

    # --- Mキャリ関連ルームの直近のやりとり・自分宛メンション ---
    mcareer_rooms = [
        r for r in client.rooms()
        if r.get("type") == "group" and is_mcareer(r.get("room_id"), r.get("name"))
    ]
    cutoff = now - timedelta(hours=RECENT_HOURS)
    mentions: List[Dict] = []
    recent: List[Dict] = []
    for room in mcareer_rooms:
        try:
            messages = client.recent_messages(room["room_id"])
        except requests.RequestException as e:
            print(f"⚠️  メッセージ取得失敗 (room {room.get('name')}): {e}")
            continue
        for m in messages:
            sent = datetime.fromtimestamp(m.get("send_time", 0), tz=JST)
            if sent < cutoff:
                continue
            account = m.get("account") or {}
            if account.get("account_id") == my_account_id:
                continue  # 自分の発言は載せない
            body_raw = m.get("body", "")
            item = {
                "room_name": room.get("name", ""),
                "sender": account.get("name", ""),
                "time": sent.strftime("%m/%d %H:%M"),
                "body": truncate(clean_chatwork_body(body_raw)),
            }
            if my_account_id and f"[To:{my_account_id}]" in body_raw:
                mentions.append(item)
            else:
                recent.append(item)

    mentions.sort(key=lambda x: x["time"], reverse=True)
    recent.sort(key=lambda x: x["time"], reverse=True)

    return {
        "my_name": me.get("name", ""),
        "mcareer_room_names": [r.get("name", "") for r in mcareer_rooms],
        "mcareer_tasks": mcareer_tasks,
        "other_tasks": other_tasks,
        "mentions": mentions,
        "recent": recent[:10],  # 多すぎると朝に読めないので最新10件まで
    }


def demo_data() -> Dict:
    """レイアウト確認用のサンプルデータ（--demo）"""
    return {
        "my_name": "ふじさき",
        "mcareer_room_names": ["【Mキャリ】AI×動画編集講座 運営"],
        "mcareer_tasks": [
            {"room_name": "【Mキャリ】AI×動画編集講座 運営", "body": "第3回講義のスライド最終版を提出", "assigned_by": "山田", "label": "今日まで", "urgency": 1},
            {"room_name": "【Mキャリ】AI×動画編集講座 運営", "body": "受講生の課題フィードバック（5名分）", "assigned_by": "山田", "label": "08/25（月）", "urgency": 2},
        ],
        "other_tasks": [
            {"room_name": "てらこ社内", "body": "月次レポートの下書き", "assigned_by": "佐藤", "label": "期限なし", "urgency": 3},
        ],
        "mentions": [
            {"room_name": "【Mキャリ】AI×動画編集講座 運営", "sender": "山田", "time": "08/21 18:30", "body": "次回の講義日程、9/2と9/4のどちらがご都合よいですか？"},
        ],
        "recent": [
            {"room_name": "【Mキャリ】AI×動画編集講座 運営", "sender": "鈴木", "time": "08/21 15:02", "body": "教材フォルダに Premiere のテンプレを追加しました。"},
        ],
    }


# ---------------------------------------------------------------------------
# HTML 生成
# ---------------------------------------------------------------------------

def _task_rows(tasks: List[Dict], accent_class: str) -> str:
    rows = ""
    for t in tasks:
        urgency_class = f"urgency-{t['urgency']}"
        rows += (
            f'    <div class="item {accent_class} {urgency_class}">\n'
            f'      <div class="item-title">{html.escape(truncate(t["body"], 90))}</div>\n'
            f'      <div class="item-meta"><span class="due">{html.escape(t["label"])}</span>'
            f' &nbsp;·&nbsp; {html.escape(t["room_name"])}'
            + (f' &nbsp;·&nbsp; 依頼: {html.escape(t["assigned_by"])}' if t.get("assigned_by") else "")
            + "</div>\n"
            "    </div>\n"
        )
    return rows


def _message_rows(messages: List[Dict], accent_class: str) -> str:
    rows = ""
    for m in messages:
        rows += (
            f'    <div class="item {accent_class}">\n'
            f'      <div class="item-title">{html.escape(m["sender"])} <span class="time">{html.escape(m["time"])}</span></div>\n'
            f'      <div class="item-body">{html.escape(m["body"])}</div>\n'
            f'      <div class="item-meta">{html.escape(m["room_name"])}</div>\n'
            "    </div>\n"
        )
    return rows


def build_briefing_html(data: Dict, date: datetime) -> str:
    date_str = date.strftime("%Y年%m月%d日")
    weekday = WEEKDAYS_JA[date.weekday()]

    out = (
        """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<style>
  body { font-family: 'Hiragino Sans', 'Helvetica Neue', sans-serif; max-width: 600px; margin: 0; padding: 20px; background: #f5f5f5; }
  .container { background: white; border-radius: 8px; padding: 30px; }
  .header { background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #fbbf24; padding: 20px; border-radius: 8px; margin-bottom: 30px; text-align: center; }
  .header h1 { margin: 0; font-size: 24px; }
  .header p { margin: 5px 0 0 0; font-size: 12px; color: #94a3b8; }
  .section { margin-bottom: 30px; }
  .section-title { font-size: 16px; font-weight: bold; color: #1e293b; margin-bottom: 15px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; }
  .item { margin-bottom: 12px; padding: 12px; background: #f8fafc; border-left: 3px solid #94a3b8; border-radius: 4px; }
  .item-title { font-weight: bold; color: #1e293b; font-size: 14px; margin-bottom: 4px; }
  .item-body { font-size: 13px; color: #475569; line-height: 1.5; margin-bottom: 4px; }
  .item-meta { font-size: 11px; color: #64748b; }
  .time { font-weight: normal; font-size: 11px; color: #64748b; }
  .due { font-weight: bold; }
  .accent-mcareer { border-left-color: #d97706; }
  .accent-mention { border-left-color: #dc2626; }
  .accent-chat { border-left-color: #0e7490; }
  .accent-other { border-left-color: #64748b; }
  .urgency-0 { background: #fef2f2; }
  .urgency-0 .due { color: #dc2626; }
  .urgency-1 { background: #fffbeb; }
  .urgency-1 .due { color: #d97706; }
  .empty { font-size: 13px; color: #64748b; padding: 4px 0; }
  .footer { text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #64748b; font-size: 12px; }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>☀️ 朝のブリーフィング</h1>
    <p>"""
        + date_str
        + "（"
        + weekday
        + """）</p>
  </div>

  <p>おはようございます！本日の状況をお届けします。</p>
"""
    )

    # --- 要返信（自分宛メンション） ---
    out += '  <div class="section">\n'
    out += '    <div class="section-title">🔔 要返信（Mキャリ・自分宛メンション）</div>\n'
    if data["mentions"]:
        out += _message_rows(data["mentions"], "accent-mention")
    else:
        out += '    <div class="empty">直近24時間で自分宛のメンションはありません。</div>\n'
    out += "  </div>\n"

    # --- Mキャリのタスク ---
    out += '  <div class="section">\n'
    out += f'    <div class="section-title">🎬 Mキャリのタスク（{len(data["mcareer_tasks"])}件）</div>\n'
    if data["mcareer_tasks"]:
        out += _task_rows(data["mcareer_tasks"], "accent-mcareer")
    else:
        out += '    <div class="empty">オープンなタスクはありません。</div>\n'
    out += "  </div>\n"

    # --- Mキャリの直近のやりとり ---
    if data["recent"]:
        out += '  <div class="section">\n'
        out += '    <div class="section-title">💬 Mキャリの直近のやりとり（24時間）</div>\n'
        out += _message_rows(data["recent"], "accent-chat")
        out += "  </div>\n"

    # --- その他の Chatwork タスク ---
    if data["other_tasks"]:
        out += '  <div class="section">\n'
        out += f'    <div class="section-title">📋 その他の Chatwork タスク（{len(data["other_tasks"])}件）</div>\n'
        out += _task_rows(data["other_tasks"], "accent-other")
        out += "  </div>\n"

    monitored = "、".join(data["mcareer_room_names"]) or "（該当ルームなし）"
    out += (
        '  <div class="footer">\n'
        f"    <p>てらこ 朝のブリーフィング | 監視中ルーム: {html.escape(monitored)}</p>\n"
        "  </div>\n"
        "</div>\n</body>\n</html>"
    )
    return out


def save_briefing_html(briefing_html: str, date: datetime) -> Path:
    # 業務内容を含むためコミット対象外のドットファイルに保存（.gitignore 済み）
    path = REPO_DIR / f".briefing-{date.strftime('%Y-%m-%d')}.html"
    path.write_text(briefing_html, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# メール送信
# ---------------------------------------------------------------------------

def send_briefing_email(briefing_html: str, date: datetime, urgent_count: int) -> bool:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    email_to = os.getenv("BRIEFING_EMAIL_TO", DEFAULT_EMAIL_TO)
    gmail_user = os.getenv("GMAIL_ADDRESS")
    gmail_pass = os.getenv("GMAIL_APP_PASSWORD")

    if not gmail_user or not gmail_pass:
        print("⚠️  Gmail credentials not configured.")
        print("   Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD to enable email delivery.")
        return False

    date_str = date.strftime("%Y年%m月%d日")
    subject = f"☀️ 朝のブリーフィング - {date_str}"
    if urgent_count:
        subject += f"（要対応 {urgent_count}件）"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = email_to
    msg.attach(MIMEText(briefing_html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(gmail_user, gmail_pass)
            server.sendmail(gmail_user, [email_to], msg.as_string())
        print(f"✓ Email sent to: {email_to}")
        return True
    except smtplib.SMTPException as e:
        print(f"❌ Email send error: {e}")
        return False


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="朝のブリーフィング生成")
    parser.add_argument("--demo", action="store_true", help="サンプルデータでHTMLを生成（API不要）")
    parser.add_argument("--no-email", action="store_true", help="メール送信をスキップ")
    args = parser.parse_args()

    now = datetime.now(JST)
    print(f"☀️ 朝のブリーフィング生成: {now.strftime('%Y-%m-%d %H:%M')} JST")

    if args.demo:
        data = demo_data()
    else:
        token = os.getenv("CHATWORK_API_TOKEN")
        if not token:
            print("❌ CHATWORK_API_TOKEN が設定されていません。BRIEFING_SETUP.md を参照してください。")
            sys.exit(1)
        client = ChatworkClient(token)
        try:
            data = gather_briefing_data(client, now)
        except requests.RequestException as e:
            print(f"❌ Chatwork API エラー: {e}")
            sys.exit(1)

    print(f"  Mキャリルーム: {len(data['mcareer_room_names'])}件 / "
          f"Mキャリタスク: {len(data['mcareer_tasks'])}件 / "
          f"その他タスク: {len(data['other_tasks'])}件 / "
          f"要返信: {len(data['mentions'])}件")

    briefing_html = build_briefing_html(data, now)
    path = save_briefing_html(briefing_html, now)
    print(f"✓ Briefing saved: {path.name}")

    if not args.no_email:
        # 「要対応」= 期限切れ・今日までのタスク + 自分宛メンション
        urgent = sum(1 for t in data["mcareer_tasks"] + data["other_tasks"] if t["urgency"] <= 1)
        urgent += len(data["mentions"])
        send_briefing_email(briefing_html, now, urgent)


if __name__ == "__main__":
    main()
