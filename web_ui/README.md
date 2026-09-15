# AI Commerce Search Catalog Mapper & Enricher (Web UI)

本ディレクトリ（`web_ui/`）は、CSV または JSONL 形式のEC商品データを入力として受け取り、**Google Cloud AI Commerce Search (Vertex AI Search for Retail / Commerce)** の **BigQuery Schema** に合わせた項目マッピング設定、および **Google Search Grounding（リアルタイムWeb検索）＋ Gemini** を活用したマルチルール・データエンリッチメント（検索タグ生成、商品説明補強、スペック属性抽出など）をブラウザ上で直感的に実行できる Web アプリケーションです。

---

## 📂 ディレクトリ・ファイル構成 (Directory Structure)

```text
/usr/local/google/home/minsoojun/work/catalog_enrichment_in_bigquery/web_ui/
├── README.md                   # Web UI 概要およびディレクトリ構成ドキュメント (本ファイル)
├── run.sh                      # Web サーバー起動スクリプト (Port 8080, Python -P オプション適用)
├── requirements.txt            # Python 依存パッケージ一覧 (FastAPI, google-genai, google-cloud-bigquery等)
├── venv/                       # Python 3.11 仮想環境 (uv により構築・パッケージ導入済み)
├── app/                        # FastAPI バックエンド・コアモジュール
│   ├── __init__.py             # パッケージ初期化ファイル
│   ├── main.py                 # FastAPI サーバー本体・API エンドポイント定義
│   │                           #   - POST /api/upload             : CSV / JSONL ファイルアップロード・自動解析
│   │                           #   - POST /api/sample             : 汎用サンプル商品データ (5件) のロード
│   │                           #   - POST /api/mapping/auto-suggest: カラム名に基づくスキーマ自動マッチング推奨
│   │                           #   - POST /api/enrichment/test-rule: 1行データに対する Google Search + Gemini 即時テスト
│   │                           #   - POST /api/process/start      : 非同期・並列バッチ Enrichment 実行
│   │                           #   - GET  /api/process/status/{id}: バッチ進捗・リアルタイムログ取得
│   │                           #   - GET  /api/export/jsonl/{id}  : BigQuery Schema 準拠 JSONL ファイル出力
│   │                           #   - POST /api/bigquery/load      : BigQuery テーブルへの直接ロード (Load Job)
│   ├── config.py               # GCP Project ID (retail-search-jp-demo-minsoo), Gemini モデル等の設定管理
│   ├── schema_manager.py       # AI Commerce Search BigQuery 31項目の定義、自動マッチング辞書、日本語プリセットプロンプト6種
│   ├── enricher.py             # Gemini + Google Search Grounding 推論エンジン、変数展開、JSON/Attributesパーサー
│   ├── transformer.py          # マッピング＆Enrichment結果の統合、BigQuery ネスト構造(attributes, priceInfo等)整形・検証
│   └── sample_data.py          # テスト用 汎用サンプル商品カタログデータ (5商品)
├── static/                     # フロントエンド Web UI (日本語対応 SPA)
│   ├── index.html              # メイン画面レイアウト (4ステップ構成 + 5種類のモーダルダイアログ)
│   ├── css/
│   │   └── style.css           # カスタムスタイルシート (Noto Sans JP フォント・スキーマバッジ等)
│   └── js/
│       └── app.js              # フロントエンド制御ロジック (動的テーブル生成、1行テスト、進捗ポーリング等)
└── tests/
    └── test_app.py             # バックエンド単体・統合テストスイート (pytest)
```

---

## 🚀 起動およびアクセス方法

### 1. Web サーバーの起動
```bash
cd /usr/local/google/home/minsoojun/work/catalog_enrichment_in_bigquery/web_ui
./run.sh
```

### 2. ブラウザからのアクセス
- **URL**: `http://minsoojun.c.googlers.com:8080` （または `http://localhost:8080`）

### 3. テストの実行
```bash
PYTHONPATH=/usr/local/google/home/minsoojun/work/catalog_enrichment_in_bigquery/web_ui \
  ./venv/bin/python -P -m pytest tests/test_app.py -v
```

---

## ✅ AI 出力品質検証（ファクトチェック ＆ 日本語校閲）

Gemini の生成結果をそのまま BigQuery に格納すると、**文章が途中で切れる**・**根拠のない記述が混入する**・
**日本語が不自然になる**といった問題が発生します。本ツールでは生成後に 3 段階の検証・自動修正を行います。

| 段階 | 処理 | 内容 |
|---|---|---|
| ① 途中切れ対策 | 出力トークン上限の自動拡張 | `finish_reason=MAX_TOKENS` を検出した場合、`8192 → 16384 → 32768` と上限を引き上げて自動再生成 |
| ② 機械チェック | `EnrichmentEngine.detect_output_issues()` | 文末の途切れ・括弧の不整合・未置換プレースホルダー・同一フレーズの繰り返し・パース失敗・空出力などを LLM なしで検出 |
| ③ AI 校閲 | `EnrichmentEngine.verify_and_fix_sync()` | 元データを唯一の一次情報として、文章の完全性／日本語の自然さ／事実の正確性／ハルシネーション／形式遵守の 5 観点でレビューし、修正済み全文を返却 |

- 修正後の出力が空になる場合は**採用せず**（デグレ防止）、`verdict="rejected"` として元の出力を保持します。
- ルールごとに「**AI検証 ON / OFF**」ボタンで切り替え可能（デフォルト ON）。一括実行画面のチェックボックスで全体のデフォルトも変更できます。
- 1行テスト画面には「AI 品質検証」パネルが表示され、**検出された問題の一覧**と**修正前 / 修正後の全文比較**を確認できます。
- 一括実行中は進捗バー横に「AI自動修正」件数がリアルタイム表示されます。

> 注: 検証パスは Gemini を追加で 1 回呼び出すため、処理時間は約 1.5〜2 倍になります。速度優先の場合は OFF にしてください。

---

## 💾 JSONL ダウンロード（BigQuery ロード用データ出力）

STEP 4「データ変換実行 ＆ AI Commerce Search BigQuery データ生成」で生成した結果は、
**BigQuery にそのままロードできる NDJSON（1行 = 1商品）ファイル**としてダウンロードできます。

| 配置場所 | ボタン | 状態 |
|---|---|---|
| STEP 4 ヘッダー右上 | `JSONL ダウンロード` | 一括実行の完了までは**グレーアウト（無効）**。完了後に「(全 N 件)」と件数を表示して有効化 |
| 実行完了パネル内 | `BigQuery JSONL ダウンロード (.jsonl)` | 完了パネル表示と同時に利用可能 |

- 出力エンドポイント: `GET /api/export/jsonl/{job_id}`（`Content-Type: application/x-ndjson`）
- ファイル名: `aics_bigquery_catalog_{job_id}.jsonl`（サーバーの `Content-Disposition` から自動取得）
- 画面下部の結果テーブルは**先頭 20 件のプレビュー**ですが、**JSONL には処理した全件**が出力されます。
  ダウンロード前に「出力対象: 全 N 件 / 推定ファイルサイズ」が表示されます。
- ダウンロードは `fetch` + `Blob` 方式で行うため、**エラー時もページ遷移せず、設定中のマッピング／Enrichment ルールは保持されます**。
  - ジョブが見つからない場合（サーバー再起動によりメモリ上のジョブが消失したケース）は、日本語のエラーメッセージを表示して再実行を促します。

```bash
# ダウンロードした JSONL を BigQuery にロードする例
bq load --source_format=NEWLINE_DELIMITED_JSON --autodetect \
  retail-search-jp-demo-minsoo:retail_search.d-vais-c ./aics_bigquery_catalog_job_xxxxxxx.jsonl
```
