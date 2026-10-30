# 収集する夏の草花

| 内部ID（旧セーブと共通） | 表示名 | 取得週 | 既存の場所 | EDの形 |
|---|---|---|---|---|
| herb_fine | ローズマリー | 6月1週 | 北側浅瀬へ向かう草地 | 針状の細い葉 |
| herb_round | スペアミント | 6月4週 | フジの作業地近くの草地 | 幅広く鋸歯のある葉 |
| herb_flower | マリーゴールド | 8月1週 | 南東の草地 | Tagetes系の黄色・橙色の花 |

マリーゴールドは観賞用のTagetes系を指し、カレンデュラではありません。飲食・薬効の説明はありません。取得説明は他の植物の取得を前提にしません。

マップは共通の光る印を使い、個別の植物絵は描きません。取得済みの種類だけを、机の隅にある「夏に集めた草花の乾燥束」に重ねます。各部品は19×31、既存の座標293・298・302,142を維持します。12品すべてを集めたときだけ眠る二人が出る条件も共通です。

保存されるのは上記の内部IDです。表示名が仮称だった時期の取得済みデータもそのまま読み込みます。通常保存・花壇保存・デバッグ中の一時保存の処理は変更しません。スタッフロール接続後の部屋も同じ描画と素材を使います。

素材は既存の部屋と植物アトラスを参照してimagegenで植物3点だけを更新し、asset_tool 0.5.4で透明色0・16色・最近傍変換しています。他の品や部屋は再生成していません。高解像度の生成元・プロンプトは部屋試作のsources/herbs_species.pngとsources/herbs_generation.json、再変換はupdate_herbs.pyです。

選定時に参照した資料：
- エスビー食品・ローズマリー：https://www.sbfoods.co.jp/customer/detail/00682.html
- エスビー食品・スペアミント：https://www.sbfoods.co.jp/customer/detail/00685.html
- KINCHO園芸・マリーゴールド：https://www.kincho-engei.co.jp/cultivation/detail/4998/
- 農研機構・Tagetesの学名と花色：https://www.naro.go.jp/laboratory/carc/organic/ryokuhi-sakumotsu/marigold.html
