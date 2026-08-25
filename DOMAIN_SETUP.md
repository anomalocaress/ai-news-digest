# 独自ドメイン（news.teraco-labo.com）の設定手順

> **重要：順序を守ってください。** `CNAME` ファイルを先に置くと、GitHub Pages は
> 即座に `news.teraco-labo.com` へのリダイレクトを開始します。DNS がまだ向いていない状態だと
> **サイトが完全に到達不能になります**（`teraco-labo.github.io/ai-news-digest` も含めて）。
> そのためリポジトリに `CNAME` は置いていません。

## 現在の状態

| 項目 | 値 |
|---|---|
| 配信URL | `https://teraco-labo.github.io/ai-news-digest` |
| 設定箇所 | `monetize_config.json` の `site.base_url`（**ここ1箇所だけ**） |

## 手順

### 1. DNSにCNAMEレコードを追加

ドメイン管理画面（お名前.com / ムームードメイン / Xserver 等）で追加します。

| 種別 | ホスト名 | 値 |
|---|---|---|
| CNAME | `news` | `teraco-labo.github.io.` |

`teraco-labo.com` 本体は `teraco-labo-website-v2` の GitHub Pages が A レコードで使っています。
`news` は別レコードなので **本体サイトには影響しません**。

### 2. 反映を確認（数分〜48時間）

```bash
dig news.teraco-labo.com CNAME +short   # teraco-labo.github.io. が返ればOK
```

**返ってくるまで次に進まないでください。**

### 3. GitHub側で独自ドメインを設定

`teraco-labo/ai-news-digest` の Settings → Pages → Custom domain に
`news.teraco-labo.com` を入力。GitHubがDNSを検証し、成功すると `CNAME` ファイルが自動生成されます。
検証が通ったら **Enforce HTTPS** にチェック（証明書発行に数分〜1時間）。

### 4. サイト側のURLを切り替える

`monetize_config.json` の1行を書き換えて push するだけです。

```json
"base_url": "https://news.teraco-labo.com",
```

その後ローカルで再構築する場合：

```bash
python seo_builder.py       # canonical / sitemap / RSS が一斉に切り替わる
python regenerate_urls.py   # ポッドキャストの feed.xml / episodes.json も切り替える
```

翌朝の自動実行でも同じ結果になるため、急ぐ必要はありません。

### 5. ポッドキャストの再登録

旧URL（`anomalocaress.github.io`）で登録していた配信先は、
2026-08-22のアカウント移管時点で既に切れています。新しいRSS URLで登録し直してください。

```
https://news.teraco-labo.com/podcast/feed.xml
```

（ドメイン設定前に登録する場合は `https://teraco-labo.github.io/ai-news-digest/podcast/feed.xml`。
独自ドメイン設定後は自動転送されるため、後から切り替えても配信は途切れません）
