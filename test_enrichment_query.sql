-- ==============================================================================
-- 1. Gemini 3.6 Flash リモートモデル(Remote Model)作成 DDL
-- BigQuery MLからVertex AIのGemini 3.6 Flashを呼び出すためのモデル定義
-- ==============================================================================
CREATE OR REPLACE MODEL `retail-search-jp-demo-minsoo.retail_search.gemini_3_6_flash`
REMOTE WITH CONNECTION `retail-search-jp-demo-minsoo.us.demo-llm-conn`
OPTIONS(ENDPOINT = 'gemini-3.6-flash');


-- ==============================================================================
-- 2. 検索タグ生成およびattributes変換テスト用 SELECT SQL
-- 対象テーブル: retail-search-jp-demo-minsoo.retail_search.d-vais-c
-- ==============================================================================
WITH source_data AS (
  SELECT
    id,
    title,
    description,
    attributes,
    -- prompt.txtに基づくプロンプト（漢字、英語表記、ひらがな、カタカナ、連濁、俗称中心）
    CONCAT(
      """# 役割
あなたはEコマース検索（AI Commerce Search / Retail Search）のインデックス最適化の専門家です。
ユーザーがどのような検索キーワード（表記揺れ、俗称、連濁など）を入力しても商品が確実にヒットするように、商品情報から検索用タグ（tags）を生成してください。

# 目的
入力された商品情報に基づき、日本のECユーザーが検索で使用する可能性の高いキーワード（漢字、英語表記、ひらがな、カタカナ等）を網羅した「検索タグ配列（JSON）」を出力してください。

# タグ生成ルール
以下の観点からキーワードを網羅し、2〜10個のタグを生成してください：
1. 表記揺れ網羅: 漢字、ひらがな、カタカナ、アルファベット・英語の各表記（例: 剃刀 / かみそり / カミソリ / razor）
2. 連濁・発音のバリエーション: 清音・濁音の揺れ（例: くちべに ↔ ぐちべに）
3. 正式名称と口語・俗称: 公的・一般的分類名と日常会話で使われる一般的な呼び方
4. ブランド・メーカー・略称: 正式ブランド名、略称、メーカー名（日英両表記）
5. 用途・効能・症状・対象: どのような悩み・目的・対象者・シーンで検索されるか
6. 形状・スペック: 剤形、容量、パッケージ特徴

# 出力形式
必ず以下のJSON形式のみを出力してください（Markdownコードブロックや解説は含めないでください）：
{"tags": ["タグ1", "タグ2", ...]}

# 入力商品情報
- タイトル: """, COALESCE(title, '')
    ) AS prompt
  FROM
    `retail-search-jp-demo-minsoo.retail_search.d-vais-c`
  WHERE
    title IS NOT NULL
  LIMIT 5 -- 【テスト用】上位5件を抽出
),

-- Step 1: BigQuery AI関数(ML.GENERATE_TEXT)を呼び出してGemini 3.6 Flashモデルを実行
generated_data AS (
  SELECT
    src.id,
    src.title,
    src.description,
    src.attributes,
    gen.ml_generate_text_llm_result,
    gen.ml_generate_text_status
  FROM
    ML.GENERATE_TEXT(
      MODEL `retail-search-jp-demo-minsoo.retail_search.gemini_3_6_flash`,
      TABLE source_data,
      STRUCT(
        0.2 AS temperature,
        4096 AS max_output_tokens, -- 思考トークン(Thinking)とタグJSONの完全出力を担保するため4096に設定
        TRUE AS flatten_json_output
      )
    ) AS gen
  JOIN
    source_data AS src
  ON
    gen.id = src.id
),

-- Step 2: LLMレスポンステキストの整形およびJSON配列のパース (ARRAY<STRING>)
parsed_data AS (
  SELECT
    id,
    title,
    attributes,
    ml_generate_text_llm_result,
    JSON_EXTRACT_STRING_ARRAY(
      TRIM(REGEXP_REPLACE(ml_generate_text_llm_result, r'^```(?:json)?|```$', '')),
      '$.tags'
    ) AS generated_tags
  FROM
    generated_data
)

-- Step 3: BigQuery attributesスキーマ(RECORD)仕様に合わせてプレビュー確認
SELECT
  id,
  title,
  -- 1) Geminiが生成した生のレスポンステキスト
  ml_generate_text_llm_result,
  -- 2) 抽出・パースされたタグ配列 (ARRAY<STRING>)
  generated_tags,
  -- 3) 既存のattributesカラム (d-vais-cテーブルは現在空配列 [])
  attributes AS original_attributes,
  -- 4) BigQuery attributesスキーマ仕様で新規作成されたtag構造体 (key: 'tags', value.text: [...])
  STRUCT(
    'tags' AS key,
    STRUCT(
      generated_tags AS text,
      CAST([] AS ARRAY<FLOAT64>) AS numbers
    ) AS value
  ) AS new_tag_attribute,
  -- 5) 最終的にattributesに反映されるプレビュー（既存のtags属性があれば置換、なければ追加）
  ARRAY_CONCAT(
    ARRAY(
      SELECT AS STRUCT a.* 
      FROM UNNEST(COALESCE(attributes, [])) AS a 
      WHERE a.key != 'tags'
    ),
    [STRUCT(
      'tags' AS key,
      STRUCT(
        generated_tags AS text,
        CAST([] AS ARRAY<FLOAT64>) AS numbers
      ) AS value
    )]
  ) AS updated_attributes_preview
FROM
  parsed_data;
