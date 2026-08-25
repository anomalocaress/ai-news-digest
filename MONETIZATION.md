# 収益化ガイド

目的：**Claude Code の月額（約30,000円）を、このサイトの収益で賄う。**

---

## 1. 現状の到達点と、正直な見通し

### 収益の計算式

```
月間収益 = PV × クリック率 × 成約率 × 単価
```

高単価案件（1件1万円）で月30,000円 = **月3件の成約**。
成約率1%・クリック率3%と置くと、必要なのは **月およそ1万PV**。

### なぜ日次ダイジェストだけでは届かないか

| 理由 | 内容 |
|---|---|
| 競合が強すぎる | 「AIニュース」はITmedia・日経xTECH・Ledge.ai等が上位を占有 |
| ストックにならない | ニュースの賞味期限は数日。89号あっても検索資産として積み上がらない |
| 検索評価のリスク | Googleは2024年3月から大規模生成コンテンツをスパム扱い。自動生成ページに広告を敷き詰めるとAdSense・ASP審査でも不利 |

**→ 日次ダイジェストは「集客と信頼の装置」に役割を限定し、検索で戦うのは `articles/` の解説記事だけにする。**

### 想定タイムライン（SNS合計フォロワー500人からの出発）

| 時期 | やること | 想定収益 |
|---|---|---|
| 1ヶ月目 | ASP登録・GA4設置・解説記事2〜3本 | 0円 |
| 2〜3ヶ月目 | 解説記事を6本まで。SNSで毎日発信 | 0〜3,000円 |
| 4〜6ヶ月目 | 検索順位がつき始める。反応のある記事を加筆 | 3,000〜15,000円 |
| 6ヶ月目以降 | 成約が出た導線を強化 | 15,000〜30,000円 |

**最短でも4〜6ヶ月かかります。** 1〜2ヶ月で3万円という話が世の中にありますが、
広告費を投下しない前提では現実的ではありません。

---

## 2. セットアップ手順

### ステップ1：アクセス解析を入れる（最優先・所要15分）

どのページが読まれ、どのリンクが押されたか分からないと改善のしようがありません。
**収益化より先にこれをやってください。**

1. [Google Analytics](https://analytics.google.com/) で測定ID（`G-XXXXXXXXXX`）を取得
2. `monetize_config.json` の `analytics.ga4_measurement_id` に貼る
3. [Google Search Console](https://search.google.com/search-console) にサイトを登録
4. サイトマップとして `sitemap.xml` を送信

アフィリエイトリンクのクリックは `affiliate_click` イベントとしてGA4に自動送信されます。

### ステップ2：ASPに登録する（所要1〜2日・審査あり）

**優先度順：**

| ASP | 登録先 | 特徴 |
|---|---|---|
| A8.net | https://www.a8.net/ | 最大手。高単価案件の本命。サイト審査なしで登録可能 |
| もしもアフィリエイト | https://af.moshimo.com/ | Amazon・楽天の提携が通りやすい。W報酬制度あり |
| バリューコマース | https://www.valuecommerce.ne.jp/ | サーバー系に強い |

登録したら、各ASPの管理画面で以下の案件を検索して提携申請します
（`monetize_config.json` の `offers` に対応するIDを用意済み）。

- `kikagaku` — キカガク長期コース（想定2万円）
- `techacademy` — TechAcademy（想定1.5万円）
- `levtech` — レバテックキャリア（想定1.5万円）
- `conoha-wing` — ConoHa WING（想定8千円）
- `xserver` — エックスサーバー（想定7千円）
- `udemy` — Udemy（想定1.5千円）
- `amazon-book` — Amazon（想定100円）

### ステップ3：リンクを設定ファイルに貼る

提携が承認されたら、発行されたアフィリエイトURLを `monetize_config.json` に貼ります。

```json
{
  "id": "kikagaku",
  "url": "https://px.a8.net/svt/ejp?a8mat=XXXXXXXX",   ← ここ
  ...
}
```

**`url` が空の案件は一切表示されません。** 提携が取れたものから順に埋めてください。
承認前のリンクを貼ったり、架空のリンクを置いたりする必要はありません。

設定できたか確認：

```bash
python monetize.py
```

### ステップ4：解説記事を書く

```bash
# 記事のひな形は articles/ に .md で置く
vim articles/your-article.md

# 下書きの見た目を確認（公開されません）
python article_builder.py --preview

# 公開ビルド
python seo_builder.py
```

**`✍️` マーカーが残っている記事は自動的に公開がブロックされます。**
「（例：〜）」のようなプレースホルダが世に出るのを防ぐための安全弁です。

狙うキーワードの一覧は `articles/_keyword-plan.md` にあります。

### ステップ5：AdSense（任意・後回しでよい）

1万PVで月300〜1,000円程度なので、これ単独では目標に届きません。
解説記事が10本を超えてから申請するのが無難です（コンテンツ不足で落ちるため）。

```json
"adsense": { "enabled": true, "client_id": "ca-pub-XXXX", "in_article_slot": "1234567890" }
```

---

## 3. 日々の運用

毎朝6時にGitHub Actionsが自動で回します（人間の作業はゼロ）。

```
ニュース収集 → 要約 → HTML生成 → SEO/収益枠を注入 → ポッドキャスト生成
  → サイト再構築（トップ/アーカイブ/記事/sitemap/RSS） → SNS投稿キット生成
  → push → メール送信
```

### 人間がやること

| 頻度 | やること |
|---|---|
| 毎日3分 | `social/YYYY-MM-DD.md` の投稿文をコピーしてXに投稿（一言足すと伸びます） |
| 週1回 | 解説記事を1本書く |
| 月1回 | ASPの管理画面を見て、成果を記録する |

```bash
# 成果が出たら記録
python revenue_tracker.py add --amount 8000 --source a8 --offer conoha-wing

# 収支を見る
python revenue_tracker.py report

# 目標までの逆算を見る
python revenue_tracker.py plan
```

`revenue.json` と `.revenue-report.html` は `.gitignore` 済みで、公開リポジトリには出ません。

### SNSネタの貯金

過去のダイジェストからも投稿文を作れます。

```bash
python social_kit.py --backfill 30   # 過去30日ぶんを social/ に生成
```

---

## 4. 守るべきルール

| 項目 | 内容 |
|---|---|
| **PR表記** | 2023年10月のステマ規制により、広告には「PR」表記が必須。`monetize.py` が自動で付けます。**外さないでください** |
| **rel属性** | アフィリエイトリンクには `rel="nofollow sponsored"` が必須。自動で付きます |
| **虚偽の体験談** | 使っていない商品を「使ってみました」と書くのは景品表示法違反。`✍️` マーカーの箇所は必ず事実だけを書く |
| **引用の範囲** | 見出し＋要約＋出典リンクは適法。全文転載は著作権侵害 |
| **記事の水増し** | AIが書いた一般論だけの記事を量産すると検索評価が下がる。実データ・実体験を必ず入れる |

---

## 5. ファイル構成

| ファイル | 役割 |
|---|---|
| `monetize_config.json` | **収益化の全設定。基本ここだけ触る** |
| `monetize.py` | SEOメタ・解析タグ・広告枠の注入 |
| `seo_builder.py` | トップ / アーカイブ / sitemap.xml / feed.xml / robots.txt の生成 |
| `article_builder.py` | 解説記事（`articles/*.md` → HTML） |
| `social_kit.py` | SNS投稿文の生成 |
| `revenue_tracker.py` | 収支の記録とレポート |
| `site_theme.py` | サイト共通のCSS・ページ骨格 |
| `articles/_keyword-plan.md` | 狙うキーワードの設計メモ |
