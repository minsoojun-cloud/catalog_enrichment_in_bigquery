import json
from typing import List, Dict, Any, Optional
from app.config import SCHEMA_FILE_PATH, PROMPT_FILE_PATH

# Embedded AI Commerce Search BigQuery Schema fallback
DEFAULT_AICS_SCHEMA = [
  {"name": "name", "type": "STRING", "mode": "NULLABLE"},
  {"name": "id", "type": "STRING", "mode": "REQUIRED"},
  {"name": "type", "type": "STRING", "mode": "NULLABLE"},
  {"name": "primaryProductId", "type": "STRING", "mode": "NULLABLE"},
  {"name": "collectionMemberIds", "type": "STRING", "mode": "REPEATED"},
  {"name": "gtin", "type": "STRING", "mode": "NULLABLE"},
  {"name": "categories", "type": "STRING", "mode": "REPEATED"},
  {"name": "title", "type": "STRING", "mode": "REQUIRED"},
  {"name": "brands", "type": "STRING", "mode": "REPEATED"},
  {"name": "description", "type": "STRING", "mode": "NULLABLE"},
  {"name": "languageCode", "type": "STRING", "mode": "NULLABLE"},
  {
    "name": "attributes",
    "type": "RECORD",
    "mode": "REPEATED",
    "fields": [
      {"name": "key", "type": "STRING", "mode": "NULLABLE"},
      {
        "name": "value",
        "type": "RECORD",
        "mode": "NULLABLE",
        "fields": [
          {"name": "text", "type": "STRING", "mode": "REPEATED"},
          {"name": "numbers", "type": "FLOAT", "mode": "REPEATED"}
        ]
      }
    ]
  },
  {"name": "tags", "type": "STRING", "mode": "REPEATED"},
  {
    "name": "priceInfo",
    "type": "RECORD",
    "mode": "NULLABLE",
    "fields": [
      {"name": "currencyCode", "type": "STRING", "mode": "NULLABLE"},
      {"name": "price", "type": "FLOAT", "mode": "NULLABLE"},
      {"name": "originalPrice", "type": "FLOAT", "mode": "NULLABLE"},
      {"name": "cost", "type": "FLOAT", "mode": "NULLABLE"},
      {"name": "priceEffectiveTime", "type": "STRING", "mode": "NULLABLE"},
      {"name": "priceExpireTime", "type": "STRING", "mode": "NULLABLE"}
    ]
  },
  {
    "name": "rating",
    "type": "RECORD",
    "mode": "NULLABLE",
    "fields": [
      {"name": "ratingCount", "type": "INTEGER", "mode": "NULLABLE"},
      {"name": "averageRating", "type": "FLOAT", "mode": "NULLABLE"},
      {"name": "ratingHistogram", "type": "INTEGER", "mode": "REPEATED"}
    ]
  },
  {"name": "expireTime", "type": "STRING", "mode": "NULLABLE"},
  {
    "name": "ttl",
    "type": "RECORD",
    "mode": "NULLABLE",
    "fields": [
      {"name": "seconds", "type": "INTEGER", "mode": "NULLABLE"},
      {"name": "nanos", "type": "INTEGER", "mode": "NULLABLE"}
    ]
  },
  {"name": "availableTime", "type": "STRING", "mode": "NULLABLE"},
  {"name": "availability", "type": "STRING", "mode": "NULLABLE"},
  {"name": "availableQuantity", "type": "INTEGER", "mode": "NULLABLE"},
  {
    "name": "fulfillmentInfo",
    "type": "RECORD",
    "mode": "REPEATED",
    "fields": [
      {"name": "type", "type": "STRING", "mode": "NULLABLE"},
      {"name": "placeIds", "type": "STRING", "mode": "REPEATED"}
    ]
  },
  {"name": "uri", "type": "STRING", "mode": "NULLABLE"},
  {
    "name": "images",
    "type": "RECORD",
    "mode": "REPEATED",
    "fields": [
      {"name": "uri", "type": "STRING", "mode": "REQUIRED"},
      {"name": "height", "type": "INTEGER", "mode": "NULLABLE"},
      {"name": "width", "type": "INTEGER", "mode": "NULLABLE"}
    ]
  },
  {
    "name": "audience",
    "type": "RECORD",
    "mode": "NULLABLE",
    "fields": [
      {"name": "genders", "type": "STRING", "mode": "REPEATED"},
      {"name": "ageGroups", "type": "STRING", "mode": "REPEATED"}
    ]
  },
  {
    "name": "colorInfo",
    "type": "RECORD",
    "mode": "NULLABLE",
    "fields": [
      {"name": "colorFamilies", "type": "STRING", "mode": "REPEATED"},
      {"name": "colors", "type": "STRING", "mode": "REPEATED"}
    ]
  },
  {"name": "sizes", "type": "STRING", "mode": "REPEATED"},
  {"name": "materials", "type": "STRING", "mode": "REPEATED"},
  {"name": "patterns", "type": "STRING", "mode": "REPEATED"},
  {"name": "conditions", "type": "STRING", "mode": "REPEATED"},
  {"name": "publishTime", "type": "STRING", "mode": "NULLABLE"},
  {
    "name": "promotions",
    "type": "RECORD",
    "mode": "REPEATED",
    "fields": [
      {"name": "promotionId", "type": "STRING", "mode": "NULLABLE"}
    ]
  }
]


def load_bigquery_schema() -> List[Dict[str, Any]]:
    if SCHEMA_FILE_PATH.exists():
        try:
            with open(SCHEMA_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_AICS_SCHEMA


def get_mappable_schema_fields() -> List[Dict[str, Any]]:
    """
    Returns structured schema definitions in Japanese optimized for UI mapping & enrichment target selection.
    """
    return [
        # Core / Required
        {"id": "id", "label": "id (商品固有ID)", "type": "STRING", "mode": "REQUIRED", "group": "Core", "default": "", "description": "商品の一意識別子 (例: 00080997740)"},
        {"id": "title", "label": "title (商品名・タイトル)", "type": "STRING", "mode": "REQUIRED", "group": "Core", "default": "", "description": "商品の正式名称・タイトル"},
        {"id": "name", "label": "name (リソースパス)", "type": "STRING", "mode": "NULLABLE", "group": "Core", "default": "", "description": "projects/*/locations/.../products/{id}"},
        {"id": "type", "label": "type (商品タイプ)", "type": "STRING", "mode": "NULLABLE", "group": "Core", "default": "PRIMARY", "description": "PRIMARY, VARIANT, COLLECTION"},
        {"id": "primaryProductId", "label": "primaryProductId (親商品ID)", "type": "STRING", "mode": "NULLABLE", "group": "Core", "default": "", "description": "VARIANTの場合の親商品ID"},
        {"id": "gtin", "label": "gtin (JANコード/EAN/UPC)", "type": "STRING", "mode": "NULLABLE", "group": "Core", "default": "", "description": "国際標準商品番号 (JANコード等)"},
        {"id": "languageCode", "label": "languageCode (言語コード)", "type": "STRING", "mode": "NULLABLE", "group": "Core", "default": "ja", "description": "ISO 639-1 言語コード (ja, en等)"},
        {"id": "uri", "label": "uri (商品詳細ページURL)", "type": "STRING", "mode": "NULLABLE", "group": "Core", "default": "", "description": "ECサイトの商品詳細ページURL"},

        # Categorization & Search
        {"id": "categories", "label": "categories (カテゴリ階層配列)", "type": "STRING", "mode": "REPEATED", "group": "Classification & Search", "default": "", "description": "例: ['家電 > エアコン > おもに6畳用']"},
        {"id": "brands", "label": "brands (ブランド・メーカー配列)", "type": "STRING", "mode": "REPEATED", "group": "Classification & Search", "default": "", "description": "ブランド名またはメーカー名配列"},
        {"id": "tags", "label": "tags (検索用タグ配列)", "type": "STRING", "mode": "REPEATED", "group": "Classification & Search", "default": "", "description": "検索インデックス最適化用キーワード・表記揺れ配列"},
        {"id": "collectionMemberIds", "label": "collectionMemberIds (コレクションメンバーID)", "type": "STRING", "mode": "REPEATED", "group": "Classification & Search", "default": "", "description": "コレクションに含まれる子商品IDリスト"},

        # Pricing & Inventory
        {"id": "priceInfo.price", "label": "priceInfo.price (販売価格)", "type": "FLOAT", "mode": "NULLABLE", "group": "Pricing & Stock", "default": "", "description": "現在の販売価格 (税込数値)"},
        {"id": "priceInfo.originalPrice", "label": "priceInfo.originalPrice (定価・通常価格)", "type": "FLOAT", "mode": "NULLABLE", "group": "Pricing & Stock", "default": "", "description": "割引前の元の価格"},
        {"id": "priceInfo.currencyCode", "label": "priceInfo.currencyCode (通貨コード)", "type": "STRING", "mode": "NULLABLE", "group": "Pricing & Stock", "default": "JPY", "description": "通貨コード (JPY, USD等)"},
        {"id": "priceInfo.cost", "label": "priceInfo.cost (原価)", "type": "FLOAT", "mode": "NULLABLE", "group": "Pricing & Stock", "default": "", "description": "商品の仕入原価"},
        {"id": "availability", "label": "availability (在庫ステータス)", "type": "STRING", "mode": "NULLABLE", "group": "Pricing & Stock", "default": "IN_STOCK", "description": "IN_STOCK, OUT_OF_STOCK, PREORDER, BACKORDER"},
        {"id": "availableQuantity", "label": "availableQuantity (在庫数量)", "type": "INTEGER", "mode": "NULLABLE", "group": "Pricing & Stock", "default": "", "description": "現在の注文可能在庫数 (整数)"},
        {"id": "availableTime", "label": "availableTime (販売開始日時)", "type": "STRING", "mode": "NULLABLE", "group": "Pricing & Stock", "default": "", "description": "ISO 8601 タイムスタンプ"},
        {"id": "publishTime", "label": "publishTime (発売日・公開日時)", "type": "STRING", "mode": "NULLABLE", "group": "Pricing & Stock", "default": "", "description": "商品の発売日 (ISO 8601)"},
        {"id": "expireTime", "label": "expireTime (掲載終了日時)", "type": "STRING", "mode": "NULLABLE", "group": "Pricing & Stock", "default": "", "description": "商品の公開終了日時"},

        # Specs & Content
        {"id": "description", "label": "description (商品説明文)", "type": "STRING", "mode": "NULLABLE", "group": "Details & Attributes", "default": "", "description": "商品の概要および詳細説明テキスト"},
        {"id": "attributes", "label": "attributes (カスタム仕様・属性 RECORD)", "type": "RECORD", "mode": "REPEATED", "group": "Details & Attributes", "default": "", "description": "[{'key': '属性名', 'value': {'text': ['値']}}]"},
        {"id": "attributes.tags", "label": "attributes[key='tags'] (attributes内の検索タグ)", "type": "RECORD_ATTR", "mode": "REPEATED", "group": "Details & Attributes", "default": "", "description": "attributes配列内の key='tags' 項目として検索タグを格納"},
        {"id": "sizes", "label": "sizes (サイズ配列)", "type": "STRING", "mode": "REPEATED", "group": "Details & Attributes", "default": "", "description": "商品のサイズ一覧 (例: ['S', 'M', 'L'])"},
        {"id": "materials", "label": "materials (素材・材質配列)", "type": "STRING", "mode": "REPEATED", "group": "Details & Attributes", "default": "", "description": "主な素材・材質 (例: ['ステンレス', 'アルミ'])"},
        {"id": "patterns", "label": "patterns (パターン・柄配列)", "type": "STRING", "mode": "REPEATED", "group": "Details & Attributes", "default": "", "description": "柄・デザインパターン"},
        {"id": "conditions", "label": "conditions (商品の状態配列)", "type": "STRING", "mode": "REPEATED", "group": "Details & Attributes", "default": "NEW", "description": "例: ['NEW'], ['REFURBISHED'], ['USED']"},
        {"id": "colorInfo.colors", "label": "colorInfo.colors (詳細カラー名配列)", "type": "STRING", "mode": "REPEATED", "group": "Details & Attributes", "default": "", "description": "具体的な色名 (例: ['ピュアホワイト', 'プラチナシルバー'])"},
        {"id": "colorInfo.colorFamilies", "label": "colorInfo.colorFamilies (標準カラー系統)", "type": "STRING", "mode": "REPEATED", "group": "Details & Attributes", "default": "", "description": "標準カラーファミリー (例: ['WHITE', 'SILVER'])"},

        # Media & Reviews
        {"id": "images.uri", "label": "images[].uri (商品画像URL)", "type": "STRING", "mode": "REPEATED", "group": "Media & Rating", "default": "", "description": "商品画像URL (カンマ区切りで複数登録可)"},
        {"id": "rating.averageRating", "label": "rating.averageRating (平均レビュー評価)", "type": "FLOAT", "mode": "NULLABLE", "group": "Media & Rating", "default": "", "description": "レビュー平均点 (例: 4.5)"},
        {"id": "rating.ratingCount", "label": "rating.ratingCount (レビュー件数)", "type": "INTEGER", "mode": "NULLABLE", "group": "Media & Rating", "default": "", "description": "総レビュー数 (整数)"},
        {"id": "audience.genders", "label": "audience.genders (対象性別)", "type": "STRING", "mode": "REPEATED", "group": "Media & Rating", "default": "", "description": "ターゲット性別配列"},
        {"id": "audience.ageGroups", "label": "audience.ageGroups (対象年齢層)", "type": "STRING", "mode": "REPEATED", "group": "Media & Rating", "default": "", "description": "ターゲット年齢層配列"},
        {"id": "promotions", "label": "promotions (プロモーションID配列)", "type": "RECORD", "mode": "REPEATED", "group": "Media & Rating", "default": "", "description": "適用プロモーションID"},
    ]


def auto_suggest_mapping(source_columns: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Intelligently suggests mappings from uploaded CSV/JSONL columns to AI Commerce Search Schema fields.
    """
    suggestions = {}
    synonyms = {
        "id": ["id", "p_cd", "product_id", "item_id", "sku", "goods_id", "code", "상품코드", "상품id", "商品コード", "商品id"],
        "title": ["title", "name", "product_name", "item_name", "goods_name", "상품명", "商品名", "タイトル"],
        "gtin": ["gtin", "jan", "jan_code", "ean", "barcode", "upc", "jancode", "바코드", "janコード"],
        "categories": ["categories", "category", "cat", "category_path", "raw_category", "breadcrumb", "카테고리", "カテゴリ"],
        "brands": ["brands", "brand", "maker", "manufacturer", "브랜드", "제조사", "ブランド", "メーカー"],
        "description": ["description", "desc", "short_desc", "summary", "detail", "body", "explanation", "상세설명", "상품설명", "商品説明"],
        "priceInfo.price": ["price", "sale_price", "intax_price", "selling_price", "가격", "판매가", "価格", "販売価格"],
        "priceInfo.originalPrice": ["original_price", "list_price", "regular_price", "정가", "원가", "定価"],
        "priceInfo.currencyCode": ["currency", "currency_code", "통화", "通貨"],
        "availableQuantity": ["quantity", "stock", "stock_qty", "available_quantity", "inventory", "재고", "在庫数", "在庫"],
        "availability": ["availability", "stock_status", "in_stock", "재고상태", "在庫状況"],
        "uri": ["uri", "url", "link", "product_url", "pdp_url", "상세url", "상품링크", "商品url"],
        "images.uri": ["image", "image_url", "images", "img_url", "thumbnail", "이미지", "画像url"],
        "rating.averageRating": ["rating", "average_rating", "score", "review_score", "평점", "レビュー評価"],
        "rating.ratingCount": ["rating_count", "review_count", "reviews", "리뷰수", "レビュー数"],
        "attributes": ["attributes", "specs", "spec", "specification", "속성", "스펙", "仕様"],
        "tags": ["tags", "tag", "keywords", "search_tags", "태그", "키워드", "検索タグ"],
        "colorInfo.colors": ["color", "colors", "colour", "색상", "カラー"],
        "sizes": ["size", "sizes", "사이즈", "サイズ"],
        "materials": ["material", "materials", "소재", "재질", "素材"],
        "publishTime": ["publish_time", "release_date", "launch_date", "출시일", "発売日"],
    }

    col_lower_map = {c.lower().strip(): c for c in source_columns}

    for target_field, candidates in synonyms.items():
        matched_col = None
        for cand in candidates:
            if cand in col_lower_map:
                matched_col = col_lower_map[cand]
                break
        if matched_col:
            suggestions[target_field] = {
                "mode": "column",
                "source_column": matched_col,
                "default_value": ""
            }

    defaults = {
        "type": "PRIMARY",
        "languageCode": "ja",
        "priceInfo.currencyCode": "JPY",
        "availability": "IN_STOCK",
        "conditions": "NEW"
    }
    for field, def_val in defaults.items():
        if field not in suggestions:
            suggestions[field] = {
                "mode": "static",
                "source_column": "",
                "default_value": def_val
            }

    return suggestions


def get_enrichment_presets() -> List[Dict[str, Any]]:
    """
    Returns built-in prompt templates in Japanese for Google Search + Gemini catalog enrichment.
    """
    return [
        {
            "id": "search_tags_jp",
            "name": "検索タグ生成 (Search Tags - 表記揺れ・連濁・俗称網羅)",
            "target_field": "tags",
            "output_format": "json_array",
            "use_google_search": True,
            "recommended_sources": ["title", "brands", "categories"],
            "prompt": """# 役割
あなたはEコマース検索（AI Commerce Search / Retail Search）のインデックス最適化の専門家です。
ユーザーがどのような検索キーワード（表記揺れ、漢字・ひらがな・カタカナ・英語表記、連濁、俗称など）を入力しても商品が確実にヒットするように、商品情報およびGoogle Search検索結果から検索用タグ（tags）を生成してください。

# 入力商品情報
- 商品名: {title}
- ブランド: {brands}
- カテゴリ: {categories}
- 説明文: {description}

# タグ生成ルール
Google Searchで該当型番・商品の特徴や一般的な呼称を確認した上で、以下の観点から15〜30個のキーワードを網羅してください：
1. 表記揺れ網羅: 漢字、ひらがな、カタカナ、アルファベット・英語の各表記（例: 剃刀 / かみそり / カミソリ / razor）
2. 連濁・発音のバリエーション: 清音・濁音の揺れ（例: かぜくすり ↔ かぜぐすり）
3. 正式名称と口語・俗称・略称（例: エアコン ↔ クーラー / ワイヤレスヘッドホン ↔ Bluetoothイヤホン）
4. ブランド・メーカー・シリーズ名（日英両表記）
5. 用途・効能・対象者・利用シーン（例: 6畳, 省エネ, 一人暮らし, 花粉対策）
6. 形状・主要スペック・搭載機能（例: インバーター, 自動お掃除, ストリーマ, ナノイー等）

# 出力形式
必ず解説やMarkdownコードブロックを含めず、以下のJSON配列形式のみを出力してください：
["タグ1", "タグ2", "タグ3", ...]"""
        },
        {
            "id": "attributes_tags_jp",
            "name": "Attributes内検索タグ追加 (attributes[key='tags'])",
            "target_field": "attributes.tags",
            "output_format": "json_array",
            "use_google_search": True,
            "recommended_sources": ["title", "brands"],
            "prompt": """# 役割
Eコマース検索エンジンのヒット率向上のため、商品の表記揺れ（漢字・ひらがな・カタカナ・英語）、類義語、型番バリエーション、用途キーワードを抽出し、JSON配列で出力してください。

# 入力商品情報
- 商品名: {title}
- ブランド: {brands}

# 出力形式
必ず以下のJSON文字列配列形式のみで回答してください（解説不要）：
["キーワード1", "キーワード2", "キーワード3", ...]"""
        },
        {
            "id": "description_enrichment",
            "name": "Web検索ベース商品説明・特徴補強 (Product Description Enrichment)",
            "target_field": "description",
            "output_format": "text",
            "use_google_search": True,
            "recommended_sources": ["title", "brands", "gtin"],
            "prompt": """# 役割
あなたはプロのECコピーライター兼家電・商品スペックの専門家です。
提供された商品名やJANコード（GTIN）をもとにGoogle Searchを実行し、メーカー公式スペック・特長・搭載機能を調査した上で、購買意欲を高め検索インデックスにも有効な詳細商品説明文を作成してください。

# 入力商品情報
- 商品名: {title}
- ブランド: {brands}
- JAN/GTIN: {gtin}
- 既存説明: {description}

# 作成指針
1. 冒頭で商品の 핵심的な魅力と主な特長を分かりやすく要約してください。
2. 主要機能および仕様（消費電力、サイズ・容量、独自技術、便利機能など）を箇条書き（●）で整理してください。
3. おすすめの利用シーンやターゲット層を記載してください。
4. Markdownコードブロック記法は使わず、テキスト本文のみを出力してください。"""
        },
        {
            "id": "spec_attributes_extractor",
            "name": "商品詳細スペック属性(Attributes Key-Value)自動抽出",
            "target_field": "attributes",
            "output_format": "attributes_kv",
            "use_google_search": True,
            "recommended_sources": ["title", "description", "gtin"],
            "prompt": """# 役割
商品情報およびGoogle Searchの検索結果を分析し、AI Commerce Searchの `attributes` カラムに格納する主要スペック（Key-Value）を抽出してください。

# 入力商品情報
- 商品名: {title}
- JAN/GTIN: {gtin}
- 商品説明: {description}

# 抽出指針
型番、適用畳数・容量、サイズ、重量、消費電力、主な機能など、検索ファセット（絞り込みフィルタ）として有用な項目を3〜8個抽出してください。

# 出力形式
必ず以下のJSONオブジェクト（Key-Value）形式のみで回答してください（解説不要）：
{
  "型番": "ATE22ASE5-WS",
  "適用畳数": "6畳",
  "冷房能力": "2.2kW",
  "特徴": ["省エネ", "水内部クリーン"]
}"""
        },
        {
            "id": "category_hierarchy",
            "name": "標準カテゴリ階層分類 (Category Hierarchy)",
            "target_field": "categories",
            "output_format": "json_array",
            "use_google_search": False,
            "recommended_sources": ["title", "description"],
            "prompt": """# 役割
商品名を分析し、AI Commerce Search標準の階層型カテゴリパス（大分類 > 中分類 > 小分類 > 細分類）を生成してください。

# 入力商品情報
- 商品名: {title}
- 説明文: {description}

# 出力形式
必ず以下のように ` > ` 区切りを用いた文字列配列JSON形式のみで出力してください：
["家電・照明 > エアコン・空気清浄機 > エアコン > おもに6畳用"]"""
        },
        {
            "id": "color_material_extractor",
            "name": "カラー名(Colors)抽出・正規化",
            "target_field": "colorInfo.colors",
            "output_format": "json_array",
            "use_google_search": True,
            "recommended_sources": ["title", "description"],
            "prompt": """# 役割
商品名および型番（例: -W, -WS, -T, -K 等の色記号）をGoogle Searchで確認し、商品の正確なカラー名称を抽出してください。

# 入力商品情報
- 商品名: {title}
- 説明文: {description}

# 出力形式
必ず以下のJSON配列形式のみで回答してください：
["ホワイト", "ピュアホワイト"]"""
        }
    ]
