-- ==============================================================================
-- Attributesカラムに生成された検索タグを直接UPDATEするSQL
-- 対象テーブル: retail-search-jp-demo-minsoo.retail_search.d-vais-c
-- モデル: retail-search-jp-demo-minsoo.retail_search.gemini_3_6_flash
-- ==============================================================================

UPDATE `retail-search-jp-demo-minsoo.retail_search.d-vais-c` AS target
SET attributes = source.updated_attributes
FROM (
  WITH source_data AS (
    SELECT
      id,
      title,
--      description,
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
      -- まだtags属性が存在しない商品のみを対象にする場合の条件（必要に応じて有効化）
      -- AND (attributes IS NULL OR NOT EXISTS(SELECT 1 FROM UNNEST(attributes) WHERE key = 'tags'))
    LIMIT 5 -- 【サンプルテスト用】上位5件のみ更新（全件反映時はこの行を削除またはコメントアウト）
  ),

  -- Step 1: BigQuery AI関数(ML.GENERATE_TEXT)を呼び出してタグを生成
  generated_data AS (
    SELECT
      src.id,
      src.attributes,
      gen.ml_generate_text_llm_result
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

  -- Step 2: レスポンスの整形およびJSON配列のパース (ARRAY<STRING>)
  parsed_data AS (
    SELECT
      id,
      attributes,
      JSON_EXTRACT_STRING_ARRAY(
        TRIM(REGEXP_REPLACE(ml_generate_text_llm_result, r'^```(?:json)?|```$', '')),
        '$.tags'
      ) AS generated_tags
    FROM
      generated_data
  )

  -- Step 3: BigQuery attributesスキーマ仕様に合わせて結合
  SELECT
    id,
    ARRAY_CONCAT(
      -- 既存のattributesから'tags'キーを除外した他の属性を保持
      ARRAY(
        SELECT AS STRUCT a.*
        FROM UNNEST(COALESCE(attributes, [])) AS a
        WHERE a.key != 'tags'
      ),
      -- 新規生成されたtags属性を追加 (key: 'tags', value.text: [...], value.numbers: [])
      [STRUCT(
        'tags' AS key,
        STRUCT(
          generated_tags AS text,
          CAST([] AS ARRAY<FLOAT64>) AS numbers
        ) AS value
      )]
    ) AS updated_attributes
  FROM
    parsed_data
  -- タグが正常に生成された場合のみ安全に更新
  WHERE
    generated_tags IS NOT NULL AND ARRAY_LENGTH(generated_tags) > 0
) AS source
WHERE
  target.id = source.id;


-- ==============================================================================
-- 更新結果の確認クエリ
-- ==============================================================================
SELECT 
  id, 
  title, 
  attributes 
FROM 
  `retail-search-jp-demo-minsoo.retail_search.d-vais-c`
WHERE 
  ARRAY_LENGTH(attributes) > 0
LIMIT 5;

-- ==============================================================================
-- 【参考】テストデータのリセット用クエリ
-- 注意: 行ごと削除するDELETEではなく、attributes属性のみ空配列に戻す安全な方法
-- ==============================================================================
-- UPDATE `retail-search-jp-demo-minsoo.retail_search.d-vais-c`
-- SET attributes = []
-- WHERE ARRAY_LENGTH(attributes) > 0;