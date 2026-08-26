# 課金トラッキング

「気づいたら請求が来ていた」を無くすための仕組みです。

## なぜ2つに分かれているのか

このリポジトリには、お金の見え方が違う2つの帳簿があります。

| ファイル | 対象 | 実体 |
|---|---|---|
| `.api-usage.json` → `api_cost_calculator.py` | **このリポジトリのコードが呼んだ API** | トークン数・文字数から計算した推定値 |
| `service_costs.json` → `service_costs.py` | **財布から出ていくお金ぜんぶ** | 請求書に基づく実額 |

前者だけを見ていると必ず取りこぼします。サブスク・前払いクレジット・無料体験からの自動移行は、
コードが1行も動かなくても課金されるからです。後者はそれを拾うための台帳です。

> 金額の実データ（`service_costs.json`）は `.gitignore` 済みです。
> このリポジトリは公開されているので、`revenue.json` と同じ扱いにしています。
> 手元に無いときは `service_costs.sample.json` から自動で作られます。

## 使い方

```bash
python service_costs.py report   # 全サービスと月額合計
python service_costs.py check    # 危ないものだけ（要対応があれば exit 1）
```

新しいサービスを契約したら、その場で足します。

```bash
python service_costs.py add \
  --id elevenlabs --name ElevenLabs --category "AI API" \
  --billing prepaid --amount 5 --currency USD \
  --dashboard https://elevenlabs.io/app/subscription \
  --note "ポッドキャストの声を替えるために契約"
```

ローカルのダッシュボード（`python dashboard_app.py` → http://localhost:8920）にも
「💳 課金しているサービス」カードとして出ます。金額はクリックでそのサービスの請求ページへ飛べます。

## fal の件（2026-08-22）

**結論: 暴走していません。自分で入れたクレジット代です。**

- 2026-08-22 15:14 GitHub 連携で fal.ai のアカウントを作成
- 2026-08-22 15:31 同額の請求書が発行され、即決済（クレジット購入）
- 請求書番号の連番が `-00001` = このアカウントで初めての請求。以降の請求は届いていない

つまり「チャージした金額」と「請求が来た金額」が同じもので、二重に取られてはいません。
このリポジトリのコードは fal を一切呼んでいません（`fal_client` も `FAL_KEY` も未使用）。

ただし fal は**前払いクレジット制**です。残高が減ったときに自動リチャージが ON だと、
使うたびに黙って再課金されます。https://fal.ai/dashboard/billing で次を確認してください。

1. 現在の残高
2. 自動リチャージ（auto top-up）が ON か OFF か
3. Usage / Billing reports に想定外のモデル呼び出しが無いか

## 台帳を見る場所

| どこで | 何ができる |
|---|---|
| Artifact（スマホ・PC どちらでも） | 一覧・警告・その場で編集・各社の解約ページへ直行 |
| `python service_costs.py report` | 手元での確認。CI やスクリプトに組み込むなら `check` |
| ローカルダッシュボード（localhost:8920） | 他の運用情報と並べて見る |

Artifact で編集して「保存して同期」を押すと全端末に反映されます。
リポジトリ側の `service_costs.json` とは自動では繋がっていないので、
大きく変えたときは手で揃えてください。

## 落とし穴の型

台帳に載せる基準は「コードを止めても課金が続くか」です。続くなら載せます。

| 型 | 例 | 危険な理由 |
|---|---|---|
| 前払いクレジット | fal, OpenAI | 自動リチャージで無限に増える |
| 無料体験からの自動移行 | Adobe, SuperGrok | 解約しないと本課金。しかも年間契約になることがある |
| 従量課金の API キー | Anthropic API, Gemini API | キーが有効なだけで、どこからでも課金できる |
| 無料枠のあるインフラ | Supabase | 枠を超えた瞬間に有料プランへ |

**捕捉の仕組み**: Apple・Google・Adobe・カード会社は、どの端末で契約しても領収書メールを送ってきます。
つまり受信箱が実質的に全デバイスの課金センサーです。iPhone で入れたサブスクも、そこで捕まえられます。

## 自動で見張る（billing_watch.py）

毎朝6時の GitHub Actions が、ダイジェスト生成のあとに受信箱を見ます。

```bash
python billing_watch.py               # 直近2日（毎朝の実行と同じ）
python billing_watch.py --days 30     # 過去30日をまとめて棚卸し
python billing_watch.py --days 7 --notify   # 見つかったらメールで知らせる
```

- 認証は **日次配信で既に使っている Gmail の App パスワード**（`EMAIL_PASSWORD`）をそのまま流用します。
  App パスワードは SMTP 送信と IMAP 読み取りの両方に効くので、新しい認証情報は要りません
- 読むのは **From / Subject / Date のヘッダだけ**。本文は取得せず、既読フラグも立てません
- 台帳の `mail_match` に載っていない送信元から課金メールが来たら「未知の課金」として通知します。
  Apple 経由のアプリ内課金が捕まるのはこの経路です
- カード利用通知のような1件ごとの雑音は `mail.ignore_senders` で落としています。
  取りこぼしが怖ければ `vpass.ne.jp` を外してください
- このステップは `continue-on-error: true` です。受信箱が読めなくても毎朝の配信は止まりません

## 月1回やること

1. `python service_costs.py check` を実行
2. 🔴 と 🟡 を潰す
3. 金額が「不明」のものは請求書を見て `service_costs.json` の `amount` を埋める
4. 使っていないサービスは `status` を `unused` か `cancelled` に落とす（合計から外れます）
