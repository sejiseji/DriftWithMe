# Asset Storage And Sheet Rules

作成日: 2026-09-12
文書バージョン: 0.1.0
目的: 合意済みのアセット保存・シート配置規約を、現在のHEADと既存リソースに照らして記録する。

## 0. 作業範囲と現行確認

- 作業開始時HEAD: `0047fe73e75a64b6f07d663a5e9112845b196ea0` (`Add optional buddy sprite hook`)
- 作業開始時の `git status --short`: 空。未コミット差分なし。
- JWP012C Fuse buddy導入開始時HEAD: `7b98528aafc2447d1ec70fc280d1eef2378ad97e` (`Prune low-value tests`)。開始時の `git status --short`: 空。未コミット差分なし。
- JWP012C Fuse 8方向拡張開始時HEAD: `625e34930b18b14e0f5a6af2bb7fea410ca52ab2` (`Increase Fuse buddy sprite scale`)。開始時の `git status --short`: 空。未コミット差分なし。
- 通常ウニスプライト導入開始時HEAD: `2e2d05f262ff036ce1cbc2eba969e34355ba18b7` (`Add Jack eight direction sprites`)。開始時の `git status --short`: 空。未コミット差分なし。
- 異常ウニスプライト導入開始時HEAD: `89b41777a82e301ca11126c410a557069a3bcf98` (`Add normal urchin sprite`)。開始時の `git status --short`: 空。未コミット差分なし。
- 古い基準コミット `e4c6c0a9736a878f0ac0c3635cfcc516992ae24d` へは戻していない。
- この規約文書の初回作成時は文書化のみ。JWP012CではFuse buddy静止スプライト1枚を既存pyxresへ追加した。通常ウニ導入ではnormal enemy用静止スプライト1枚を既存pyxresへ追加した。異常ウニ導入ではabnormal enemy用静止スプライト1枚を既存pyxresへ追加した。入力、カメラ、当たり判定、浮遊、影、深度順、SE、パレット、Web配布方針は変更していない。
- `docs/current_asset_rendering_contract.md` は画像導入前、基準コミット `e4c6c0a...` 時点の記録である。現在のJack pyxres導入後の状態は、本書、`docs/jwp011c_jack_pyxres_integration.md`、`docs/jwp012a_buddy_sprite_hook.md` を優先して参照する。

## 1. 現行アセットと読み込み先

現在の実行時アセット設定は `src/drift_with_me/data/game_config.json` の `assets` で管理されている。

|項目|現行値|
|---|---|
|`sprite_rendering_enabled`|`true`|
|`manifest`|`assets/jack_sprite.json`|
|`player_idle_asset`|`jack_idle_32`|
|Jack direction assets|`jack_front_32`, `jack_front_right_32`, `jack_right_32`, `jack_back_right_32`, `jack_back_32`, `jack_back_left_32`, `jack_left_32`, `jack_front_left_32`|
|`buddy_idle_asset`|`fuse_front_right_neutral_48`|
|`normal_urchin_idle_asset`|`normal_urchin_idle_32`|
|`abnormal_urchin_idle_asset`|`abnormal_urchin_inward_hands_64`|
|`fallback_to_primitives`|`true`|

現行の実行時リソース:

- manifest: `src/drift_with_me/assets/jack_sprite.json`
- pyxres: `src/drift_with_me/assets/jack_sprite.pyxres`
- Jack/Fuse/urchin source HEX: `src/drift_with_me/assets/jack_*_00.hex`, `src/drift_with_me/assets/fuse_*_neutral.hex`, `src/drift_with_me/assets/normal_urchin_idle_00.hex`, `src/drift_with_me/assets/abnormal_urchin_*_00.hex`
- `.pyxpal`: 同梱なし

`jack_sprite.json` の `load_options` は画像を読み込み対象にし、tilemap、sound、musicを除外する。pyxres本体も `tilemaps = []`、`sounds = []`、`musics = []` で、既存SEの上書き対象は確認されなかった。

## 2. 画像バンク使用状況

`src/drift_with_me/assets/jack_sprite.pyxres` の `pyxel_resource.toml` を確認した結果は次の通り。

|画像バンク|現行用途|実データ|source rect|規約上の扱い|衝突|
|---:|---|---|---|---|---|
|0|キャラクター|Jack 8方向、Fuse neutral 8方向、通常ウニidle、異常ウニcomposite|Jack `(0/32,0/64/96,32,32)`, `(0,32,32,32)`, `(0,128,32,32)` / Fuse `(128/176,0/40/80/120,48,40)` / Abnormal urchin `(0,160,64,64)` / Normal urchin `(64,160,32,32)`|現行Jack、Fuse、通常ウニ、異常ウニを維持。ヒューズpose差分・ウニ方向/状態差分等を追加する候補|なし|
|1|なし|空|なし|将来のエフェクト用に予約|なし|
|2|なし|空|なし|予備。今回用途を固定しない|なし|

注意:

- 予約は配置台帳上の区分であり、空白画像の書き込みやバンク初期化を意味しない。
- バンク番号は保存領域の用途であり、描画優先順位ではない。
- `pyxel.load()` は画像バンク群を追記せず置き換える前提で扱う。アセット個別pyxresを順番に読むだけで追加できる設計にしない。
- 今後アセットが増える場合は、既存画像を保持することを確認したうえで、ゲーム側で使用するリソースへ統合する。
- JWP012C時点では、Jack予約案とFuse frame `(128,0,48,40)` に競合はない。予約領域へは対応アセット受領時まで何も書き込まない。
- 通常ウニ受領パックの配置候補 `(0,288,32,32)` は現行256x256バンクの範囲外だったため、移動や上書きではなく空き領域 `(64,160,32,32)` へ焼き込んだ。既存Jack/Fuse領域との衝突はない。
- 異常ウニv0.4はUV未割当で、旧候補 `(x,288)` / `(x,320)` は使用しない指示だった。空き領域 `(0,160,64,64)` へcompositeを焼き込み、通常ウニ `(64,160,32,32)` と隣接するが重なっていない。

## 3. 保存方式の方針

以前の「すべての実行用画像をpyxresへ集約」「常にHEXを制作正本とする」という一律方針は、今後すべてのアセットへ必須条件として適用しない。用途に応じたハイブリッド管理とする。

|種別|当面の扱い|
|---|---|
|キャラクターなど、方向・動作差分や細かな画素編集が多いもの|`.pyxres` への焼き込みを基本にする|
|静止した背景・小物など|HEX等の定義ファイル保持を基本にし、必要なら焼き込みへ変更する|
|光の筋・粒子・波紋・感情記号など|当面はソース・演出定義を維持し、画像編集が便利な部品だけ将来焼き込む|

これは「キャラクター以外は焼き込み禁止」という意味ではない。定義から描く画像も、初期化・読込時に画像化して再利用し、毎フレームHEXを解析しない。

容量対策、動的ロード、外部画像への移行、複雑なパッカー、出力・同期・保護ツールは必要になってから別作業にする。今回先行実装しない。

## 4. キャラクター配置規約

キャラクター画像は固定枠を使い、基本は縦に方向、横にアニメーションのコマを並べる。

- 同一アニメーション内の枠寸法、アンカー、透過色を揃える。
- 透明余白を勝手に切り詰めたり、コマごとに身体を自動中央寄せしたりしない。
- 方向は絵の見え方を表す名前で管理し、ワールドX/Zと直接同一視しない。
- 反転はアセットの許可情報に従う。未制作方向を無断で反転、描き足し、再減色しない。
- 予約されているが未制作の枠を、アニメーションのフレームとして参照しない。

### 4.1 Jackの現行配置

現行Jackはバンク0に8方向の静止スプライトを持つ。`jack_idle_32` は既存の基準絵として維持し、`jack_front_left_32` は同じ `(0,0)` の画素を参照する別名として追加した。

|asset|frame|source rect|source_hash|
|---|---|---|---|
|`jack_idle_32`|`idle_00`|`(0,0,32,32)`|`9e63b51c48c928394fc992bda83c1c851588f69ba4dae7be7e340054d885cd7d`|
|`jack_front_left_32`|`front_left_00`|`(0,0,32,32)`|`9e63b51c48c928394fc992bda83c1c851588f69ba4dae7be7e340054d885cd7d`|
|`jack_front_right_32`|`front_right_00`|`(32,0,32,32)`|`173a29c11bf5952a27e37a3a501a8ac5f941c9de0eb7e424238b30fca39784ab`|
|`jack_front_32`|`front_00`|`(0,32,32,32)`|`5cf48ead95a750c893f45e925bbe33d8deb5e778945e33e78fd74e4fc003cf6f`|
|`jack_left_32`|`left_00`|`(0,64,32,32)`|`ddeb02e3d1ff05281c9fb0ebfadf94c31ca7c66ff55ba5ac273ae68be160d419`|
|`jack_back_left_32`|`back_left_00`|`(32,64,32,32)`|`48d752c3ea5e5c4669306669cb7159953d637615e09d22edd58a9f30f171b5a0`|
|`jack_right_32`|`right_00`|`(0,96,32,32)`|`00792669416356148de3d10ec2320cf6013e94f71328aac9670319b02934dfd8`|
|`jack_back_right_32`|`back_right_00`|`(32,96,32,32)`|`c3f00558ffc3b6cf579e96cfd730e406501859602d26a3fb5b785f9b6c19d72a`|
|`jack_back_32`|`back_00`|`(0,128,32,32)`|`19848ca6c4c3e4df4670ae62824943a054aed4fe56a3a57320aa605a3f67d7b6`|

いずれも画像バンク0、32x32、colkey 0、anchor_px `(16,32)`、world_size `(16.0,16.0)`、projection_mode `upright_height_billboard_v1`、flip_policy `none`。制作正本HEXは `src/drift_with_me/assets/jack_*_00.hex` に保持する。

8方向導入時も、表示寸法、hover、影、深度順、collider、入力、カメラは変更していない。方向はJackの最後の移動を画面上へ投影し、`right`, `front_right`, `front`, `front_left`, `left`, `back_left`, `back`, `back_right` の8分割で選ぶ。該当アセットがない場合のみ `jack_idle_32` へフォールバックする。

### 4.2 Jackの初期配置台帳案

以下は今後のアニメーション追加用の配置案。方向のコマ0の一部は実データとして使用中で、未記載セルは予約のみであり、書き込みや参照は行わない。

|行|用途|コマ0|コマ1|コマ2|コマ3|
|---|---|---|---|---|---|
|基準絵|現行 `idle_00`|`(0,0)` 実データ|未割当|未割当|未割当|
|front|正面系|`(0,32)` 実データ|`(32,32)`|`(64,32)`|`(96,32)`|
|left|左向き|`(0,64)` 実データ|`(32,64)` は `back_left` 実データ|`(64,64)`|`(96,64)`|
|right|右向き|`(0,96)` 実データ|`(32,96)` は `back_right` 実データ|`(64,96)`|`(96,96)`|
|back|背面系|`(0,128)` 実データ|`(32,128)`|`(64,128)`|`(96,128)`|

すべて32x32枠の左上座標。`front_right` は `(32,0)` に配置済み。方向切替は実装済みだが、歩行アニメーションやコマ追加は今後のアセット導入時の作業とする。

### 4.3 Fuse buddyの現行配置

JWP012Cでは、`drift_with_me_fuse_parts_v0_2` から合成済みneutral 8方向を実行用pyxresへ焼き込んだ。

|direction|asset|source rect|source_hash|
|---|---|---|---|
|front|`fuse_front_neutral_48`|`(128,40,48,40)`|`a9c9661505e49fbf9d42a4e2f066c2a668b68677d844eb8eaa8000620460189c`|
|front_right|`fuse_front_right_neutral_48`|`(128,0,48,40)`|`669450adbdc57c659942a737164f6727866ef22ac129e647f621482442d850f8`|
|right|`fuse_right_neutral_48`|`(176,40,48,40)`|`e4d70c506274fec641c01111add437712777f7e7c6f67101dcbd3c15ffbab5e8`|
|back_right|`fuse_back_right_neutral_48`|`(128,80,48,40)`|`4ade96bae2660569dea2826941e5853f100ab218aaf00ef1dd85b1d39d93ef57`|
|back|`fuse_back_neutral_48`|`(176,80,48,40)`|`f36e148c68b10c0f99cdeb0732f90e53d0d074af8f953cd5501d09ca06c19058`|
|back_left|`fuse_back_left_neutral_48`|`(128,120,48,40)`|`18fba52bce98e9a0277f0a0e0d6ed6ba6a886dad4397ae8f50f43b73ce4ec926`|
|left|`fuse_left_neutral_48`|`(176,120,48,40)`|`f7d1a7b3f13c1a57e5505b7706cb03a82721a0197f6b7db1fdb8b56e74838d95`|
|front_left|`fuse_front_left_neutral_48`|`(176,0,48,40)`|`3d4f0deba3774002fa4b205c89ce56569e4721eaabd73b7e3bf8ef9a7c10cf13`|

全方向ともcanvas 48x40、colkey 2、anchor_px `(24,30)`、world_size `(25.2,21.0)`。制作正本として、同じ画素を `src/drift_with_me/assets/fuse_*_neutral.hex` に保持する。透明色は2であり、0は黒い不透明色として扱う。

この `world_size` は既存の高さベース `upright_height_billboard_v1` で使う実効キャンバス寸法である。JWP012C直後の実機確認で縮小時に片目が消えやすかったため、16px基準から求めた初期値へ全方向共通の可読性倍率を足した。buddyの追従、高さ、bob、影、深度ソート、コリジョンなし設定は変更していない。

方向選択はプレイヤーの直近移動方向を画面上の8方向へ丸めて選ぶ。未接続のpose差分、パネルアニメーション、buddy固有の注視方向制御は将来作業とする。未制作方向を反転や補完で増やさない。

### 4.4 通常ウニの現行配置

`drift_with_me_normal_urchin_v0_1` から、通常ウニの静止スプライト1枚を実行用pyxresへ焼き込んだ。

|asset|frame|source rect|source_hash|
|---|---|---|---|
|`normal_urchin_idle_32`|`idle_00`|`(64,160,32,32)`|`a9e16f5b554a53f4492849cf05f937e3657a2b0aed64bd46f13357148f850d03`|

canvas 32x32、colkey 0、anchor_px `(16,32)`、world_size `(20.0,20.0)`。制作正本として、同じ画素を `src/drift_with_me/assets/normal_urchin_idle_00.hex` に保持する。

このアセットは `enemy.kind == "normal"` の表示だけに使う。異常ウニの表示は別アセット `abnormal_urchin_inward_hands_64` で管理する。敵AI、接触半径、guard/barrier、capture、SEは変更していない。状態リングなどの演出は引き続きコード駆動であり、画像の再生完了や見た目にゲーム判定を依存させない。

### 4.5 異常ウニの現行配置

`drift_with_me_abnormal_urchin_redesign_v0_4` から、異常ウニの合成済み静止スプライト1枚を実行用pyxresへ焼き込んだ。

|asset|frame|source rect|source_hash|
|---|---|---|---|
|`abnormal_urchin_inward_hands_64`|`composite_00`|`(0,160,64,64)`|`9def2c00c1daaf9642812966229d1f2d6afbc04269cad3e1bdd246fbb76e0f4b`|

canvas 64x64、colkey 0、anchor_px `(32,62)`、world_size `(20.0,20.0)`。制作正本として、同じ画素を `src/drift_with_me/assets/abnormal_urchin_composite_00.hex` に保持し、部品確認用にbody/hand/handsのHEXも同じディレクトリへ保存する。

ゲームではcompositeだけを描画する。body、hand_screen_left、hand_screen_rightを別々に重ねる経路は今回実装しない。左右手の名称は画面基準であり、左右反転や8方向化はしない。

このアセットは `enemy.kind == "abnormal"` の表示だけに使う。通常ウニは `normal_urchin_idle_32` のまま維持し、敵AI、接触半径、bubble capture、discharge、guard/barrier、SEは変更していない。状態リング、突進予告線、捕獲リングなどの演出は引き続きコード駆動であり、画像の再生完了や見た目にゲーム判定を依存させない。

## 5. エフェクト配置・描画規約

バンク1は将来の水滴、泡、波紋、火花、音符、光の模様などのために予約する。今回、実データは置かない。

- 配置の基準は8px単位。
- 小粒は8x8、少し大きい形は16x16、泡の破裂などは32x32を候補とする。寸法の強制ではない。
- 光の模様など、用途に応じた長方形も許可する。
- 同じエフェクトのコマは横に並べる。種類やバリエーションは領域を分ける。
- 具体的な領域確保はアセット受領時に行い、今はシート全体を細分化して埋めない。
- 再生順、フレーム時間、ループ条件は配置とは別の定義とする。
- 中心、足元、発生点など、エフェクトごとの意味を持つアンカーを指定する。
- 透過色はアセットに明記する。シート全体で透過色を一つに強制せず、同一クリップ内では統一する。

画像にしない情報は、コードまたは定義側に保持する。対象には軌道、速度、発生数、寿命、発火条件、対象追従、時間の進み方、消費資源、命中・捕獲・撃退判定を含む。

画像を変更したり描画をカリングしたりしても、既存の攻撃成立や資源消費を変更しない。ゲーム判定は見た目の再生完了へ無条件に依存させない。図形生成が適切な光筋・波紋等は、図形描画を続けてよい。

将来の描画分類:

|意味上の区分|例|原則|
|---|---|---|
|地面・水面に付くもの|波紋、足元の広がり|地面側に置き、必要な物体に隠れる|
|ワールド内のもの|飛ぶ水滴、泡、火花、塵|必要に応じ既存の深度順へ混ぜる|
|画面に重ねるもの|集中線、画面全体の演出|ワールド後、通常UI前を基本にする|
|可読性優先の追従記号|頭上の音符・感情記号|追従位置と遮蔽方針を個別に指定する|

この分類は規約上の意味であり、新しい汎用レイヤーエンジンを今回作る指示ではない。エフェクトをバンク1に置いた理由だけで、すべてを画面最前面へ描かない。

## 6. メタデータと編集正本

保存先を呼び出し側へ直書きしない。アセットID、動作、方向、フレームを元に、描画元と切り出し領域を解決する方針を維持する。UVやバンク番号をゲームロジック各所へ直接追加しない。

アセット追加時には、既存のmetadata形式を優先して再利用し、今回新スキーマへ移行しない。少なくとも次を記録する。

- アセットID・版
- 保存先と、画像バンク・切り出し領域またはソース定義
- 寸法・透過色・アンカー
- フレーム一覧・時間・方向・反転方針
- 描画方法・表示寸法・深度や遮蔽の扱い
- 編集正本の場所と、生成処理による上書き可否

正本はアセットごとに一つにする。

- 定義管理ではHEX等を正本とし、画像はそこから生成する。
- `.pyxres` を直接編集し始める場合は、対象領域を編集正本とするか、編集結果を元ソースへ反映するかを明記する。
- 旧HEXを無条件に再焼き込みし、採用済みの手編集を消さない。
- 同じ領域に独立した二つの正本を作らない。
- 新しい書き込みは指定領域だけを対象とし、無関係な領域や既存SE・パレットを変更しない。
- 将来の再焼き込み確認では、画像の色番号を比較する。アーカイブのバイト列だけで画素差分を判定しない。

現行Jackについて、repo内に存在する実行用正本は `jack_sprite.pyxres` と `jack_sprite.json` である。制作元HEXはこのrepo内では確認対象外だったため、将来Jackを再焼き込みする場合は、採用済み画素との色番号一致または編集正本の移管を明示してから行う。

## 7. まだ実装しないこと

- Fuseのpose差分、パネルアニメーション、buddy固有の注視方向制御の追加。
- ウニ方向差分、ウニの状態アニメーション、異常ウニの部品別描画の追加。
- 新しいエフェクト、動的ロード、外部画像への移行、パッカー、容量対策。
- パレット、SE、Web配布方針の変更。
- 既存Jack領域の移動、上書き、再パッキング。
- 新しいJWP番号の推測採番。

## 8. 初回規約文書作成時の完了チェック

- [x] 現在HEADと既存変更を記録し、巻き戻していない。
- [x] キャラクター/エフェクトの保存領域を区別し、既存配置との衝突有無を記載した。
- [x] 予約と実データ、保存先と描画順を区別した。
- [x] Jackの現行配置・画素・挙動を変更していない。
- [x] アセットごとの編集正本と、手編集領域の保護方針を記載した。
- [x] 新しい絵、エフェクト、パッカー、移行処理を実装していない。
- [x] 文書以外の変更がないことをdiffで確認した。

JWP012Cでは新しいFuse静止スプライト1枚を実装対象として追加したため、上記の「新しい絵を実装していない」は初回規約文書作成時の履歴であり、現在の到達点ではない。

## 9. 未確認事項

- iPhone実機での見た目、操作、SE再生は今回未実施。
- Fuseのpose差分、ウニ方向/状態差分、街、小物、エフェクトの具体的な画素と正本は未接続。
- `CODEX_PYXRES_UPDATE.md` という既存文書は現在のrepo内では確認されなかった。外部指示として存在する場合、本書のハイブリッド管理方針を今後の参照先とする。
