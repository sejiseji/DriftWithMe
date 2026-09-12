# JWP012C Fuse Buddy Sprite

作業日: 2026-09-12

## 基準

- 作業開始時HEAD: `7b98528aafc2447d1ec70fc280d1eef2378ad97e` (`Prune low-value tests`)
- 作業開始時の `git status --short`: 空。未コミット差分なし。
- 受領パック: `drift_with_me_fuse_parts_v0_2.zip`
- 既存のJack導入、buddy描画フック、入力、カメラ、SE、当たり判定は維持する。

## 導入内容

今回接続したのは、Fuse buddyの合成済み静止画1枚のみ。

|項目|値|
|---|---|
|asset id|`fuse_front_right_neutral_48`|
|source HEX|`src/drift_with_me/assets/fuse_front_right_neutral.hex`|
|source frame|`composites/front_right__neutral.hex`|
|source hash|`669450adbdc57c659942a737164f6727866ef22ac129e647f621482442d850f8`|
|image bank|0|
|source rect|`(128,0,48,40)`|
|canvas|48x40 px|
|colkey|2|
|anchor_px|`(24,30)`|
|opaque bounds|`(13,11,35,35)` exclusive|
|projection|`upright_height_billboard_v1`|
|runtime config|`assets.buddy_idle_asset = "fuse_front_right_neutral_48"`|

透明色は2。色番号0は黒い不透明色として扱う。

## 表示寸法

受領パックの補足指示では、Fuse本体は16px基準で、現行buddyの `cube_size=6.0` に対応させる。

既存の描画経路は `world_size[1]` とフレーム高から等方スケールを求めるため、JWP012Cでは投影コードを増やさず、メタデータの `world_size` に実効キャンバス寸法を記録した。

```text
world_size = (19.86080254132485, 16.550668784437377)
```

これは48x40キャンバスの縦横比を保ち、pitch 25deg の既存FOLLOW基準で16px相当の本体が6world相当に見えるようにするための値。buddyのモデル寸法、追従、浮遊、影、深度ソート、活動範囲、コリジョンなし設定は変更していない。

## 変更しないこと

- Fuseの残りposeや方向差分はまだ接続しない。
- ランタイム合成、パネル点滅、方向選択、左右反転は実装しない。
- 既存Jack領域は移動しない。
- SE、tilemap、music、paletteはpyxresロード対象から外したままにする。
- 入力、カメラ、投影コード、判定、水/電力、敵AIは変更しない。

## 検証

- `.venv/bin/python -m pytest tests/test_hex_assets.py`: 16 passed。
- `.venv/bin/python scripts/check_all.py`: PASS。spec data、pytest 59件、ruff、format check、compileall、web build、`git diff --check` を通過。
- `.venv/bin/python -c "from drift_with_me.app import DriftWithMeApp; DriftWithMeApp(headless=True, smoke_frames=5)"`: 終了コード0。

未実施:

- iPhone実機での表示確認。
- Fuseの残りpose、方向差分、パネルアニメーションの接続。
