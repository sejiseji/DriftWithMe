# Jack World P0 — Codex用仕様パック v0.1.0

**広い正方形の陸地を、立方体のジャックと小立方体のヒューズで探索するPyxelプロトタイプ。**

正式なゲームタイトルは未決定です。このパックは仕様書と初期データであり、ゲームを実装済みのソースパッケージではありません。

## 最初に渡すもの

Codexへこのフォルダ一式を渡し、[CODEX_START_HERE.md](CODEX_START_HERE.md) のプロンプトを使ってください。最初の作業範囲は **JWP000〜JWP002**。まず正方形マップでの自由歩行、モバイル入力・表示、簡易SEの土台を作ります。

## 収録内容

| ファイル | 内容 |
|---|---|
| [SPEC.md](SPEC.md) | 操作、座標、投影、衝突、カメラ、敵、連携、資源、SE、カリング、Webの詳細仕様 |
| [CODEX_START_HERE.md](CODEX_START_HERE.md) | 貼り付け用の開始指示と既存コード保護方針 |
| [TASKS.md](TASKS.md) | JWP000〜JWP008の9ウェーブと完了ゲート |
| [ACCEPTANCE.md](ACCEPTANCE.md) | 自動／手動を分けた112件の受入テスト計画 |
| [data/game_config.json](data/game_config.json) | 単位付きの初期調整値 |
| [data/prototype_world.json](data/prototype_world.json) | 大きな正方形地面と検証用オブジェクト配置 |
| [data/audio_events.json](data/audio_events.json) | 5種類のSEと判定イベントの対応 |
| [tools/validate_spec_data.py](tools/validate_spec_data.py) | 標準ライブラリだけで動く初期データ検証器 |
| [SOURCES.md](SOURCES.md) | API・端末表示・Web配布の公式参照先 |
| [VALIDATION_REPORT.md](VALIDATION_REPORT.md) | このパック作成時に実施した検査と未実施範囲 |

## 初期値の要約

| 項目 | v0.1.0の初期案 |
|---|---|
| 地面 | 32×32セル、1セル32単位、1024×1024の平坦な正方形 |
| 自キャラ | 一辺16の立方体、自由XZ移動 |
| ヒューズ | 一辺6の立方体、飛翔追従 |
| 画面 | 仮512×236。426×196 / 640×294も比較 |
| PC表示 | 同じ論理解像度の2〜3倍、収まらなければfit |
| カメラ | 浅い俯瞰、追従、調査FOCUS、全景ゾーン、限定的な角度変更 |
| 敵 | 通常ウニ2、異常個体1 |
| 対処 | 水バリアで押す／泡で捕獲して手動電撃 |
| 資源 | 水100、行動電力60を仮値。補給地点から回復 |
| 音 | 発射・捕獲・押し返し・電撃成功・使用不可の5SE |
| 対象外 | 完成絵、BGM、リアルタイム昼夜、自由カメラ、HP・死亡、複雑な地形 |

寸法・速度・消費量・UI閾値は実装開始のための仮値で、実機計測で決めた最適値ではありません。確定している世界観と、調整可能な実装値を分けて扱います。

## 添付データの検証

このフォルダのルートで：

```sh
python3 tools/validate_spec_data.py --self-test
```

これはJSON・初期配置の検査です。Pyxelの起動試験、iPhoneの入力・音声・性能確認は行いません。ゲーム側の試験はACCEPTANCEに従って、実装後に別途実施してください。
