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
│   │                           #   - POST /api/sample             : EDION 家電サンプルデータ (5件) のロード
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
│   └── sample_data.py          # テスト用 EDION 家電サンプルカタログデータ (5商品)
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
