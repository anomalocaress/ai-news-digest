# メール送信設定ガイド

## 概要

毎日朝6時（JST）に自動生成されたAIニュースダイジェストのHTML形式メールを `fujisaki@teraco-labo.com` に送信します。

## セットアップ方法

### 1. Gmail アプリパスワード取得

メール送信には Gmail のアプリパスワードが必要です：

1. [Google アカウント セキュリティ](https://myaccount.google.com/security) にアクセス
2. 左側メニューから「セキュリティ」を選択
3. 「2段階認証プロセス」が有効になっていることを確認
4. 下にスクロールして「アプリパスワード」をクリック
5. 「メール」と「Windows パソコン」を選択
6. 表示されるパスワードをコピー

### 2. 環境変数設定

#### ローカルテスト用（.env ファイル）

```bash
# .env ファイルに追加
GMAIL_ADDRESS=your-email@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

#### GitHub Actions 用

リポジトリの Settings → Secrets and variables → Actions で以下を追加：

| 名前 | 値 |
|------|-----|
| `GMAIL_ADDRESS` | メールアドレス（例：user@gmail.com） |
| `GMAIL_APP_PASSWORD` | Google アプリパスワード（スペース含む） |

### 3. GitHub Actions ワークフロー設定

`.github/workflows/generate-news.yml` を確認して、以下の環境変数が設定されていることを確認：

```yaml
steps:
  - name: Generate news digest
    env:
      GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
      GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
      # ... その他の環境変数
```

## メール送信の流れ

```
6:00 AM JST
  ↓
GitHub Actions 起動
  ↓
generate_news.py 実行
  → HTML メール生成
  → SMTP 経由で Gmail 送信
  → fujisaki@teraco-labo.com に配信
```

## トラブルシューティング

### メールが届かない場合

1. **環境変数の確認**
   ```bash
   echo $GMAIL_ADDRESS
   echo $GMAIL_APP_PASSWORD
   ```

2. **アプリパスワードの確認**
   - スペース区切り（4文字×4グループ）になっていることを確認
   - コピー時にスペースが含まれていることを確認

3. **2段階認証の有効化確認**
   - Gmail セキュリティ設定で2段階認証が有効か確認
   - アプリパスワードは2段階認証が有効な場合のみ利用可能

4. **ログ確認**
   - GitHub Actions のログで詳細なエラーメッセージを確認

### ローカルテスト

```bash
# 環境変数を設定
export GMAIL_ADDRESS="your-email@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"

# テスト実行
python3 generate_news.py --date 2026-04-24
```

## メール内容

送信されるメールには以下が含まれます：

- ✅ カテゴリ別AI ニュース（モデル・研究・ビジネス・ポリシー・ツール）
- ✅ ポッドキャスト再生リンク
- ✅ Spotify RSS フィード
- ✅ ユーザー評価に基づく推奨トピック

## セキュリティに関する注意

- アプリパスワードは GitHub Secrets で安全に保管
- メール送信は SMTP SSL/TLS で暗号化
- 本番環境では環境変数の値は絶対にリポジトリにコミットしない
