# 朝のブリーフィング設定ガイド（Mキャリ × Chatwork 連携）

## 概要

毎朝 6:15（JST）に、Chatwork から以下を取得してブリーフィングメールを届けます：

- 🔔 **要返信** — Mキャリ関連ルームでの直近24時間の自分宛メンション
- 🎬 **Mキャリのタスク** — 自分に割り当てられたオープンタスク（期限切れ→今日→期限順）
- 💬 **Mキャリの直近のやりとり** — 関連ルームの最近のメッセージ（最新10件）
- 📋 **その他の Chatwork タスク** — Mキャリ以外のルームの自分のタスク

ブリーフィング HTML には業務内容が含まれるため、**リポジトリにはコミットされません**
（`.briefing-*.html` は gitignore 済み。メール送信のみ）。

## セットアップ方法

### 1. Chatwork API トークン取得

1. Chatwork にログインし、右上のプロフィール写真をクリック
2. 「サービス連携」を選択
3. 左メニューの「API Token」を開く
4. パスワードを入力してトークンを表示し、コピー

※ API トークンは自分のアカウントの全ルームにアクセスできる強い権限です。
絶対にリポジトリにコミットしないでください。

### 2. GitHub Secrets / Variables 設定

リポジトリの Settings → Secrets and variables → Actions で設定：

**Secrets（必須）**

| 名前 | 値 |
|------|-----|
| `CHATWORK_API_TOKEN` | 手順1で取得したトークン |
| `GMAIL_ADDRESS` | 送信元 Gmail アドレス（設定済みなら不要） |
| `EMAIL_PASSWORD` | Gmail アプリパスワード（設定済みなら不要） |

※ `GMAIL_ADDRESS` / `EMAIL_PASSWORD` はニュースダイジェストと共通です。

**Variables（任意）**

| 名前 | 説明 | デフォルト |
|------|------|-----------|
| `CHATWORK_MCAREER_KEYWORD` | ルーム名でMキャリ関連と判定するキーワード（カンマ区切り可） | `Mキャリ,エムキャリ` |
| `CHATWORK_MCAREER_ROOM_IDS` | ルームIDで明示指定（カンマ区切り）。指定時はキーワードより優先 | なし |

ルーム名に「Mキャリ」が含まれていればデフォルト設定のままで動きます。
含まれていない場合は、Chatwork でルームを開いたときの URL `#!rid12345678` の
数字部分（`12345678`）を `CHATWORK_MCAREER_ROOM_IDS` に設定してください。

### 3. 動作確認

Actions タブ → 「Generate Morning Briefing」→ Run workflow で手動実行できます。

## ローカルの LINE ブリーフィングへの組み込み

Mac ローカルで実装中の LINE 送信版ブリーフィングからは、このスクリプトを
「Chatwork/Mキャリ情報の取得部品」として呼び出せます（メール送信は行われません）：

```bash
# LINE メッセージにそのまま使えるプレーンテキスト（LINE上限に合わせ4900字で切り詰め済み）
CHATWORK_API_TOKEN="xxxx" python3 generate_briefing.py --format text

# 自前のメッセージ組み立てに使う場合は構造化JSON
CHATWORK_API_TOKEN="xxxx" python3 generate_briefing.py --format json
```

- どちらも**標準出力にデータだけ**が出ます（ログは標準エラー）ので、
  そのままパイプ・変数取り込みできます
- JSON のキー: `date` / `my_name` / `mcareer_room_names` /
  `mcareer_tasks`・`other_tasks`（`body`, `label`, `urgency` 0=期限切れ 1=今日 2=3日以内 3=それ以降, `room_name`, `assigned_by`）/
  `mentions`・`recent`（`sender`, `time`, `body`, `room_name`）
- 取得には Chatwork API トークンが必要です（取得方法は上記手順1）

## ローカルテスト

```bash
# API を使わずレイアウトだけ確認（.briefing-YYYY-MM-DD.html が生成される）
python3 generate_briefing.py --demo --no-email

# 実データで確認（メール送信なし）
export CHATWORK_API_TOKEN="xxxxxxxx"
python3 generate_briefing.py --no-email

# メール送信まで通す
export GMAIL_ADDRESS="your-email@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"
python3 generate_briefing.py
```

## 実行の流れ

```
6:15 AM JST（ニュースダイジェストの15分後）
  ↓
GitHub Actions 起動
  ↓
generate_briefing.py 実行
  → Chatwork API からタスク・メンション・メッセージを取得
  → HTML ブリーフィング生成（コミットはしない）
  → SMTP 経由で Gmail 送信
  → fujisaki@teraco-labo.com に配信
```

## トラブルシューティング

- **401 Unauthorized** — トークンが無効。Chatwork で再発行して Secrets を更新
- **Mキャリのタスクが「その他」に出る** — ルーム名にキーワードが含まれていない。
  `CHATWORK_MCAREER_ROOM_IDS` でルームIDを明示指定する
- **メールが届かない** — [EMAIL_SETUP.md](EMAIL_SETUP.md) のトラブルシューティングを参照
- **メッセージが取れない** — Chatwork API のレート制限は 5分あたり300リクエスト。
  ルーム数が非常に多い場合は `CHATWORK_MCAREER_ROOM_IDS` で絞る
