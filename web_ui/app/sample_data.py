from typing import List, Dict, Any

SAMPLE_PRODUCT_DATA: List[Dict[str, Any]] = [
    {
        "p_cd": "00080997740",
        "product_name": "ダイキン 「標準工事代金半額」 6畳 エアコン e angle select Eシリーズ ATE22ASE5-WS",
        "maker": "ダイキン",
        "jan_code": "2800080997744",
        "raw_category": "エアコン・空気清浄機・加湿器 > エアコン > おもに6畳用",
        "intax_price": "99800",
        "stock_qty": "196",
        "pdp_url": "https://example.com/products/00080997740",
        "image_url": "https://example.com/images/product/7744/02800080997744/300x300/2800080997744_1.jpg",
        "short_desc": "一般の市販モデル(AN225AES-W)をベースに仕様変更・追加したオリジナルモデル。水内部クリーン・ストリーマ搭載。"
    },
    {
        "p_cd": "00078123450",
        "product_name": "パナソニック ヘアードライヤー ナノケア アルティメイト EH-NC80-T オーセンティックブラウン",
        "maker": "パナソニック",
        "jan_code": "4549980789124",
        "raw_category": "美容・健康 > ドライヤー・ヘアアイロン > ヘアドライヤー",
        "intax_price": "84150",
        "stock_qty": "42",
        "pdp_url": "https://example.com/products/00078123450",
        "image_url": "https://example.com/images/product/3450/4549980789124/300x300/4549980789124_1.jpg",
        "short_desc": "高浸透ナノイー（第2世代）搭載。髪質に合わせて4つのパーソナルメニューを選択可能な最高峰モデル。"
    },
    {
        "p_cd": "00075667890",
        "product_name": "シャープ 加湿空気清浄機 プラズマクラスターNEXT ホワイト KI-TX75-W",
        "maker": "シャープ",
        "jan_code": "4974019234561",
        "raw_category": "エアコン・空気清浄機・加湿器 > 空気清浄機 > 加湿空気清浄機",
        "intax_price": "62800",
        "stock_qty": "85",
        "pdp_url": "https://example.com/products/00075667890",
        "image_url": "https://example.com/images/product/7890/4974019234561/300x300/4974019234561_1.jpg",
        "short_desc": "プラズマクラスターNEXT搭載ハイグレードモデル。加湿量900mL/hの大容量加湿と自動掃除パワーユニット。"
    },
    {
        "p_cd": "00074321980",
        "product_name": "ソニー ワイヤレスノイズキャンセリングステレオヘッドセット WH-1000XM5 プラチナシルバー",
        "maker": "ソニー",
        "jan_code": "4548736132573",
        "raw_category": "オーディオ・楽器 > ヘッドホン・イヤホン > ワイヤレスヘッドホン",
        "intax_price": "49500",
        "stock_qty": "120",
        "pdp_url": "https://example.com/products/00074321980",
        "image_url": "https://example.com/images/product/1980/4548736132573/300x300/4548736132573_1.jpg",
        "short_desc": "統合プロセッサーV1と高音質ノイズキャンセリングプロセッサーQN1のデュアルプロセッサー構成で業界最高クラスの静寂を実現。"
    },
    {
        "p_cd": "00079011223",
        "product_name": "ダイソン コードレススティッククリーナー Dyson V12 Detect Slim Fluffy SV46FF",
        "maker": "ダイソン",
        "jan_code": "5025155081235",
        "raw_category": "生活家電 > 掃除機 > コードレススティッククリーナー",
        "intax_price": "74800",
        "stock_qty": "65",
        "pdp_url": "https://example.com/products/00079011223",
        "image_url": "https://example.com/images/product/1223/5025155081235/300x300/5025155081235_1.jpg",
        "short_desc": "Fluffy Opticクリーナーヘッドで微細なホコリを可視化。ピエゾセンサーがゴミの量とサイズを計測し吸引力を自動調整。"
    }
]


def get_sample_data() -> Dict[str, Any]:
    columns = list(SAMPLE_PRODUCT_DATA[0].keys())
    return {
        "filename": "sample_product_catalog.csv",
        "columns": columns,
        "rows": SAMPLE_PRODUCT_DATA,
        "total_rows": len(SAMPLE_PRODUCT_DATA)
    }
