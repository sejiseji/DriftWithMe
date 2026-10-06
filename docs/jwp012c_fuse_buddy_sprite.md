# JWP012C Fuse Buddy Sprite

作業日: 2026-09-12
更新日: 2026-09-13

## 基準

- 作業開始時HEAD: `7b98528aafc2447d1ec70fc280d1eef2378ad97e` (`Prune low-value tests`)
- 作業開始時の `git status --short`: 空。未コミット差分なし。
- 受領パック: `drift_with_me_fuse_parts_v0_2.zip`
- 既存のJack導入、buddy描画フック、入力、カメラ、SE、当たり判定は維持する。

## 導入内容

今回接続したのは、Fuse buddyの合成済みneutral 8方向。

|direction|asset id|source frame|source rect|source hash|
|---|---|---|---|---|
|front|`fuse_front_neutral_48`|`front__neutral`|`(128,40,48,40)`|`a9c9661505e49fbf9d42a4e2f066c2a668b68677d844eb8eaa8000620460189c`|
|front_right|`fuse_front_right_neutral_48`|`front_right__neutral`|`(128,0,48,40)`|`669450adbdc57c659942a737164f6727866ef22ac129e647f621482442d850f8`|
|right|`fuse_right_neutral_48`|`right__neutral`|`(176,40,48,40)`|`e4d70c506274fec641c01111add437712777f7e7c6f67101dcbd3c15ffbab5e8`|
|back_right|`fuse_back_right_neutral_48`|`back_right__neutral`|`(128,80,48,40)`|`4ade96bae2660569dea2826941e5853f100ab218aaf00ef1dd85b1d39d93ef57`|
|back|`fuse_back_neutral_48`|`back__neutral`|`(176,80,48,40)`|`f36e148c68b10c0f99cdeb0732f90e53d0d074af8f953cd5501d09ca06c19058`|
|back_left|`fuse_back_left_neutral_48`|`back_left__neutral`|`(128,120,48,40)`|`18fba52bce98e9a0277f0a0e0d6ed6ba6a886dad4397ae8f50f43b73ce4ec926`|
|left|`fuse_left_neutral_48`|`left__neutral`|`(176,120,48,40)`|`f7d1a7b3f13c1a57e5505b7706cb03a82721a0197f6b7db1fdb8b56e74838d95`|
|front_left|`fuse_front_left_neutral_48`|`front_left__neutral`|`(176,0,48,40)`|`3d4f0deba3774002fa4b205c89ce56569e4721eaabd73b7e3bf8ef9a7c10cf13`|

全方向ともimage bank 0、canvas 48x40 px、colkey 2、anchor_px `(24,30)`、projection `upright_height_billboard_v1`。透明色は2。色番号0は黒い不透明色として扱う。

## 表示寸法

受領パックの補足指示では、Fuse本体は16px基準で、現行buddyの `cube_size=6.0` に対応させる。

既存の描画経路は `world_size[1]` とフレーム高から等方スケールを求めるため、JWP012Cでは投影コードを増やさず、メタデータの `world_size` に実効キャンバス寸法を記録した。実機確認で縮小時に片目が消えやすかったため、画素は変更せず、全方向共通の可読性倍率として表示寸法だけを引き上げた。

```text
world_size = (25.2, 21.0)
```

これは48x40キャンバスの縦横比を保つ。buddyのモデル寸法、追従、浮遊、影、深度ソート、活動範囲、コリジョンなし設定は変更していない。

## 横向き時の位置補正

2026-09-13に、Jackが画面上の左右へ向いている時だけ、FuseがJackの背後側へ素早く滑らかに回り込む補正を追加した。

- 右向き時: Fuseのgoalを画面左側へ置く。
- 左向き時: Fuseのgoalを画面右側へ置く。
- 正面/背面が優勢な時: 従来のカメラ相対goalを維持する。
- 横向き補正中のみ `side_reposition_follow_tau_sec=0.08` を使い、通常の `follow_tau_sec=0.18` より速く寄せる。

この補正はbuddyのgoalと追従速度だけを変える。コリジョン、入力、攻撃判定、SE、スプライト画素、pyxres配置は変更していない。

## 変更しないこと

- Fuseの残りposeはまだ接続しない。
- ランタイム合成、パネル点滅、buddy固有の注視方向制御、左右反転は実装しない。
- 既存Jack領域は移動しない。
- SE、tilemap、music、paletteはpyxresロード対象から外したままにする。
- 入力、カメラ、投影コード、判定、水/電力、敵AIは変更しない。

## 検証

- `.venv/bin/python -m pytest tests/test_hex_assets.py`: 24 passed。
- `.venv/bin/python scripts/check_all.py`: PASS。spec data、pytest 67件、ruff、format check、compileall、web build、`git diff --check` を通過。
- `.venv/bin/python -c "from drift_with_me.app import DriftWithMeApp; DriftWithMeApp(headless=True, smoke_frames=5)"`: 終了コード0。

未実施:

- iPhone実機での表示確認。
- Fuseの残りpose、パネルアニメーションの接続。
