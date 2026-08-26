# タスクの目的
BigQueryに格納されている商品データを参照し、漢字、英語表記、ひらがな、カタカナ検索などでも商品が確実にヒットするように検索用タグ（tags）を生成し、商品データテーブルの `attributes` カラムに反映（UPDATE）するSQLを作成することです。

# 具体的な指針
1. BigQueryの商品テーブルのスキーマは `AI_Commerce_Search_Bigquery_schema.json` に定義されています。
2. スキーマの各カラムの説明は `data_mapping.md` に定義されています。
3. テーブルのカラムのうち `title`（および必要に応じて `description`）を使用してBigQueryのAI関数（またはVertex AI）を呼び出し、タグを生成します。
4. 最終成果物は、`attributes` に生成されたタグを追加・更新するSQL（UPDATE文）を作成することです。
