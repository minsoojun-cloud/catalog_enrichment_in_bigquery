| Schema Field | BigQuery Type | EDION HTML extraction logic / Default value | Example Value |
|---|---|---|---|
| `name` | STRING (NULLABLE) | `projects/*/locations/global/catalogs/default_catalog/branches/0/products/{p_cd}` 또는 `{p_cd}` | `"00080997740"` |
| `id` | STRING (REQUIRED) | URL 쿼리 파라미터 `p_cd` | `"00080997740"` |
| `type` | STRING (NULLABLE) | 기본값 `"PRIMARY"` | `"PRIMARY"` |
| `primaryProductId` | STRING (NULLABLE) | `null` | `null` |
| `collectionMemberIds` | REPEATED STRING | `[]` | `[]` |
| `gtin` | STRING (NULLABLE) | `dl.modelInfo` 내 `DT: JANコード`에 대응하는 `DD` 값 | `"2800080997744"` |
| `categories` | REPEATED STRING | `application/ld+json` (BreadcrumbList)에서 카테고리 계층 조합 (`Category1 > Category2 > ...`) | `["エアコン・空気清浄機・加湿器・除湿機 > エアコン > エアコンおもに6畳 2.2kw > スタンダードエアコン"]` |
| `title` | STRING (REQUIRED) | `<h1>` 태그의 텍스트 | `"ダイキン 「標準工事代金半額」 6畳 エアコン e angle select Eシリーズ ATE22ASE5-WS"` |
| `brands` | REPEATED STRING | `<h1>` 제목의 첫 단어 또는 브랜드 텍스트 | `["ダイキン"]` |
| `description` | STRING (NULLABLE) | `div.inBox` 또는 상품 설명 요약 텍스트 | `"●一般の市販モデル(型番:AN225AES-W)をベースに仕様変更・追加したオリジナルモデル!..."` |
| `languageCode` | STRING (NULLABLE) | 기본값 `"ja"` | `"ja"` |
| `attributes` | REPEATED RECORD | `dl.spec` (스펙 정보) 및 `dl.modelInfo` (型番 등) 키-값 쌍 | `[{"key": "型番", "value": {"text": ["ATE22ASE5-WS"]}}, {"key": "冷房能力", "value": {"text": ["2.2(0.6～2.8)kW"]}}]` |
| `tags` | REPEATED STRING | 카테고리 태그 또는 `[]` | `["エアコン", "スタンダードエアコン"]` |
| `priceInfo` | RECORD (NULLABLE) | `currencyCode`: `"JPY"`, `price`: `class="intaxPrice"` 수치, `originalPrice`: `price`와 동일 수치 설정 | `{"currencyCode": "JPY", "price": 99800.0, "originalPrice": 99800.0}` |
| `rating` | RECORD (NULLABLE) | 리뷰 평균 점수 및 수 (존재 시) | `{"averageRating": 4.5, "ratingCount": 3}` |
| `expireTime` | STRING (NULLABLE) | `null` | `null` |
| `ttl` | RECORD (NULLABLE) | `null` | `null` |
| `availableTime` | STRING (NULLABLE) | 수집 시점 ISO 8601 타임스탬프 | `"2026-08-05T00:00:00Z"` |
| `availability` | STRING (NULLABLE) | 페이지 내 '売り切れ'/'在庫なし' 유무에 따라 `"IN_STOCK"` 또는 `"OUT_OF_STOCK"` | `"IN_STOCK"` |
| `availableQuantity` | INTEGER (NULLABLE) | '在庫数XX台'에서 파싱된 정수 값 | `196` |
| `fulfillmentInfo` | REPEATED RECORD | `[]` | `[]` |
| `uri` | STRING (NULLABLE) | 상품 상세 페이지 URL | `"https://www.edion.com/detail.html?p_cd=00080997740"` |
| `images` | REPEATED RECORD | 상품 이미지 URL (`/ito/product/.../300x300/...`) 리스트 | `[{"uri": "https://www.edion.com/ito/product/7744/02800080997744/300x300/2800080997744_1.jpg", "height": 300, "width": 300}]` |
| `audience` | RECORD (NULLABLE) | `null` | `null` |
| `colorInfo` | RECORD (NULLABLE) | `null` | `null` |
| `sizes` | REPEATED STRING | `[]` | `[]` |
| `materials` | REPEATED STRING | `[]` | `[]` |
| `patterns` | REPEATED STRING | `[]` | `[]` |
| `conditions` | REPEATED STRING | `["NEW"]` | `["NEW"]` |
| `publishTime` | STRING (NULLABLE) | `dl.modelInfo` 내 `発売日` (YYYY年MM月DD日) -> ISO 8601 변환 | `"2025-03-01T00:00:00Z"` |
| `promotions` | REPEATED RECORD | `[]` | `[]` |
