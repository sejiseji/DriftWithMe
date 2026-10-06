# JWP011B HEX Sprite Foundation

作業開始HEAD: `e4c6c0a9736a878f0ac0c3635cfcc516992ae24d`

作業開始時の未追跡ファイル:

- `docs/current_asset_rendering_contract.md`

## 実装済み

- HEXスプライトのmanifest読み込み、メタデータ検査、HEX行列検査。
- `0`〜`F`の色番号をPyxel `Image`へ転送し、`pget`で全画素を読み戻す一致検査。
- `upright_height_billboard_v1`の投影アンカー計算。
- Pyxel `blt(scale=...)`の中心拡縮を吸収する描画アダプター。
- Jack描画のみ、設定で有効化できる任意スプライト経路。
- デフォルトは `assets.sprite_rendering_enabled=false`。アセット未提供時は既存の仮図形描画を維持する。
- 実行時ロード失敗は `asset_error: ...` を一度出し、対象描画は仮図形へ戻す。

## 現在の受け入れ形式

manifestは `schema_version: 1` と `assets` 配列を持つJSON。
各assetは以下を必須とする。

- `schema_version`
- `id`
- `palette_id: "pyxel_default_16"`
- `hex_width`, `hex_height`
- `colkey`
- `anchor_px`
- `world_size`
- `projection_mode: "upright_height_billboard_v1"`
- `flip_policy: "none"`
- `frames`
- `animation: "static"`
- `source_hash`

`source_hash` は、行優先の色番号バイト列をSHA-256にした小文字hex。
初版はstatic 1フレームのみ。

## 未実装・未確認

- Astra納品のJack本番HEX接続。
- buddy、ウニ、プロップ、歩道、地面模様の差し替え。
- アニメーション、左右反転、アトラスパッキング。
- 不透明画素に沿った遮蔽シルエット。
- 実機iPhoneでの画像経路性能測定。
