# DriftWithMe Current Asset Rendering Contract

作成日: 2026-09-12
対象: 本番HEXスプライト導入前の現行P0描画仕様
基準コミット: `e4c6c0a9736a878f0ac0c3635cfcc516992ae24d` (`Add guard action for normal urchins`)

## 0. 作業範囲とHEAD確認

- 作業開始時HEADは基準コミット `e4c6c0a9736a878f0ac0c3635cfcc516992ae24d` と一致していた。
- 作業開始時の `git status --short` は空で、未コミット差分はなかった。
- この文書は読み取り結果の記録のみを目的とする。描画方式、入力、衝突、カメラ、データ形式は変更しない。
- 本文書追加以外のコード変更は行わない。
- 外部制作のHEXスプライトを導入する準備資料であり、Codex側でドット絵の描き直し、再減色、美術補完は行わない。

## 1. 論理解像度と拡大方式

### 1.1 論理解像度

設定正本は `src/drift_with_me/data/game_config.json` の `display`。

| profile | 論理px |
|---|---:|
| `low` | 426 x 196 |
| `medium` | 512 x 236 |
| `high` | 640 x 294 |

- default profile は `medium`、つまり 512 x 236 論理px。
- UI基準高さは 236 論理px。
- ゲーム内部の描画、入力座標、カメラviewportは論理pxで扱う。

関連:

- `src/drift_with_me/config.py`
- `src/drift_with_me/data/game_config.json`
- `src/drift_with_me/app.py`

### 1.2 PCネイティブ

`pyxel.init()` は `runtime.screen_width`, `runtime.screen_height`, `display_scale` を使う。

- default logical size: 512 x 236
- desktop scale: 2
- 想定されるPyxelウィンドウ表示サイズ: 1024 x 472 表示px相当

注意:

- OSやRetina/HiDPIによる物理ピクセル換算は未確認。
- 本文書では、ゲーム内部の値は論理pxとして記録する。

関連:

- `DriftWithMeApp.__init__`
- `RuntimeConfig.desktop_scale`

### 1.3 Web/GitHub Pages

Webホストは `scripts/build_web.py` で生成される。

- Pyxel Web runtime: `pyxel.VERSION`。現行は 2.9.9。
- Pyxel virtual gamepad は `gamepad: "disabled"`。
- `window.__driftWithMeLogicalSize` に default profile の logical size を埋め込む。
- `host.js` は Canvas の `getBoundingClientRect()` からCSS表示pxを取得し、logical sizeへ逆変換する。
- `host.css` はbody固定、overflow hidden、touch-action none、portrait messageを提供する。

Webでの実表示px:

- CanvasのCSS表示サイズはPyxel Web runtime側にも依存する。
- `host.css` 自体はCanvasへ明示的な幅/高さ指定をしていない。
- そのため実表示pxは端末viewportとPyxel runtimeのレイアウト結果で決まる。未実測値は確定しない。

関連:

- `scripts/build_web.py`
- `docs/host.css`
- `docs/host.js`
- `index.html`, `docs/index.html`, `web/index.html`

## 2. ワールド座標系と地面・高さ

### 2.1 座標系

`prototype_world.json` の `coordinate_system` が正本。

| 軸 | 意味 |
|---|---|
| X | 地面上の第1軸 |
| Y | 高さ。正が上 |
| Z | 地面上の第2軸 |

- 地面は Y=0。
- オブジェクト位置は原則として足元/ルート位置。
- 主要なゲームロジックはX/Z平面で処理し、Yは描画高さに使う。

### 2.2 地面

- 32 x 32 cells。
- cell size は 32 world units。
- world bounds は X/Z ともに 0.0 から 1024.0。
- `default_walkable` は true。
- `cell_overrides` は空。

### 2.3 高さの扱い

- Jackと静的boxは `draw_box()` に世界寸法を渡して8頂点を投影する。
- 2Dプロップは足元rootとtopを投影し、画面上の矩形サイズを算出する。
- buddyはゲーム状態として `y=26.0` 付近を飛ぶ。
- 敵は描画アンカーとして `y=4.0` を投影する。
- bubbleは `y=5.0` を投影する。
- 影はY=0上に描画される。

関連:

- `src/drift_with_me/data/prototype_world.json`
- `WorldData`
- `Renderer.draw_box`
- `Renderer.sprite_prop_bounds`

## 3. カメラ仕様

### 3.1 共通投影

`CameraState.project()` が3D world座標を2D logical pxへ投影する。

- yaw/pitchはdegreeで設定され、内部でradianに変換。
- `basis` は camera position, forward, right, up を返す。
- `depth = dot(point - camera_position, forward)`。
- near/far外、非finite座標は `None`。
- horizontal FOV基準で、`f = viewport_width / (2*tan(horizontal_fov/2))`。
- screen x/y は `anchor_x * viewport_width`, `anchor_y * viewport_height` を中心に計算。

関連:

- `src/drift_with_me/math3d.py`
- `CameraState`
- `CameraState.project`

### 3.2 通常FOLLOW

設定値:

| 項目 | 値 |
|---|---:|
| yaw | 20.0 deg |
| pitch | 25.0 deg |
| horizontal FOV | 38.0 deg |
| base distance | 480.0 |
| zoom | 1.0 |
| actual distance | 480.0 |
| near / far | 8.0 / 1800.0 |
| screen anchor | (0.5, 0.58) |
| deadzone fraction | (0.18, 0.12) |
| follow tau | 0.12 sec |

`CameraController.follow_shot()` がこの値を使う。

### 3.3 Overview zone

`overview_north` はプレイヤーが X/Z 640.0から896.0の矩形に入ると有効になる。

| 項目 | 値 |
|---|---:|
| target | (768.0, 0.0, 768.0) |
| yaw | 35.0 deg |
| pitch | 25.0 deg |
| zoom | 0.7 |
| actual distance | 480 / 0.7 = 685.714... |
| enter blend | 0.8 sec |
| leave blend | 0.6 sec |
| exit margin | 32.0 |
| freeze_world | false |

関連:

- `CameraController.resolve_active_zone_id`
- `CameraController.zone_shot`
- `prototype_world.json` の `camera_zones`

### 3.4 Focus

FOCUSは調査開始時、またはdebugの `F` で開始される。

- focus target = `player_center * 0.35 + obj_center * 0.65`
- `player_center.y = player.cube_size * 0.5`
- `obj_center.y = max(12.0, object.height * 0.5)`
- yaw/pitchは現在のbase shotを継承。
- zoomは `zoom_max = 1.35`。
- actual distance は `480 / 1.35 = 355.555...`。
- anchorは `(0.5, 0.4)`。
- blend in は 0.35 sec。
- return blend は 0.5 sec。
- focus中は `CameraController.freezes_world == True`。

関連:

- `CameraController.start_focus_demo`
- `CameraController.focus_shot`
- `CameraController.update_focus`
- `DriftWithMeApp.process_events`

### 3.5 pan_demo

debugの `P` で開始される。

- sequence id: `pan_demo`
- freeze_world: true
- cue 1: `maintenance_unit`, zoom 0.9, blend 0.7 sec, hold 0.5 sec
- cue 2: `observation_post`, zoom 0.7, blend 0.8 sec, hold 0.5 sec
- cue 3: current baseへ戻る, blend 0.5 sec
- yaw/pitch指定がcueにないためbase shotを継承。

関連:

- `CameraController.start_pan_demo`
- `CameraController.resolve_cue_shot`
- `prototype_world.json` の `camera_sequences`

## 4. 描画パイプライン

`Renderer.draw_scene()` の順序:

1. `pyxel.cls(1)`
2. `draw_ground()`
3. `draw_safe_zones()`
4. `world_commands()` で描画コマンド生成
5. `sorted(commands, key=(-depth, layer_bias, stable_id))` の順に描画
6. `draw_barrier()`
7. Jackが遮蔽されていれば `draw_player_outline()`
8. `draw_interaction_marker()`
9. `draw_action_marker()`
10. effects
11. debug world

現在の描画はPyxel primitive中心。

使われている主なAPI:

- `cls`
- `tri`
- `rect`
- `rectb`
- `circ`
- `circb`
- `elli`
- `line`
- `pset`
- `text`

現行コードで使われていないもの:

- `pyxel.blt`
- `pyxel.image`
- `pyxel.load`
- `pyxel.pal`
- `colkey`
- sprite atlas / image bank

## 5. 対象別の現行描画仕様

### 5.1 Jack

データ:

- root: `(player.x, 0.0, player.z)`
- collider half extents: X/Zともに 8.0
- cube size: 16.0 world units
- visual hover config: base 2.0, amplitude 1.5, period 1.6 sec

描画:

- shadow: Y=0のrootを投影し、黒 `elli`。
- shadow radius: `max(3, int(1200 / depth))`
- body: `draw_box()`。
- box half: 8.0 x 8.0
- box height: 16.0
- color: 11
- y_offset: 現行実装では `(2.0 + sin(t/1.6*tau)) * 0.75`。実値範囲はおおむね 0.75から2.25。

sort anchor:

- `Vec3(player.x, 0.0, player.z)`
- hoverはsort depthに入らない。

関連:

- `GameModel.player_cube_size`
- `Renderer.draw_player`
- `Renderer.draw_box`

### 5.2 buddy

データ:

- cube size: 6.0 world units
- logical position: `BuddyState(x, y, z)`
- 初期/目標height: 26.0
- physical collision: false
- follow offsetはcamera relative。

描画:

- shadow: Y=0へ黒 `elli`。
- shadow radius: `max(2, int(700 / depth))`
- body: `draw_box()`。
- box half: 3.0 x 3.0
- box height: 6.0
- y_offset: `buddy.y + bob`
- bob: `sin(presentation_time * tau / 1.3) * 2.0`
- color: 10

sort anchor:

- `Vec3(buddy.x, buddy.y, buddy.z)`
- bobはsort depthに入らない。

関連:

- `GameModel.buddy_cube_size`
- `GameModel.buddy_goal`
- `Renderer.draw_buddy`

### 5.3 通常ウニ

データ:

- kind: `normal`
- collision radius: 10.0 world units
- move speed: 6.0
- aggro radius: 80.0
- home leash: 128.0

描画:

- projection anchor: `Vec3(enemy.x, 4.0, enemy.z)`
- screen radius: `max(3, int(900 / depth))`
- base color: 8
- state color:
  - `REPELLED`: 12
  - `REST`: 13
  - `RETURN_HOME`: 5
  - `CAPTURED`: 12
  - `WINDUP`: 8
  - `RECOVER`: 13
- body: `circ`
- spikes: 8本の `line`、radiusからradius+3へ伸ばす。
- `APPROACH`: outer `circb(radius+4, 8)`
- `REST`: top line

sort anchor:

- `Vec3(enemy.x, 0.0, enemy.z)`

関連:

- `GameModel.enemy_radius`
- `Renderer.draw_enemy`

### 5.4 異常ウニ

データ:

- kind: `abnormal`
- collision radius: 10.0 world units
- approach speed: 32.0
- dash speed: 180.0
- aggro radius: 128.0
- windup range: 112.0
- windup: 0.75 sec
- dash duration: 0.45 sec
- recover: 1.2 sec
- home leash: 160.0

描画:

- projection anchor, screen radius, spikesは通常ウニと同じ。
- base color: 2
- `WINDUP`: warning lineをworld lineで56 world units分描画し、`circb(radius+5, 8)`。
- `DASH`: `circb(radius+5, 2)`。
- `CAPTURED`: world circle radius 16.0 color 12 と `circb(radius+5, 12)`。

sort anchor:

- `Vec3(enemy.x, 0.0, enemy.z)`

関連:

- `GameModel.update_abnormal_enemy`
- `Renderer.draw_enemy`

### 5.5 Bubble

データ:

- speed: 240.0
- collision radius: 10.0
- max range: 128.0
- max projectiles: 1

描画:

- projection anchor: `Vec3(bubble.x, 5.0, bubble.z)`
- screen radius: `max(3, int(600 / depth))`
- `circb` color 12
- center `pset` color 7

sort:

- depth from `Vec3(bubble.x, 4.0, bubble.z)` in command generation
- `layer_bias = -1`
- stable id: `"bubble"`

関連:

- `BubbleState`
- `Renderer.draw_bubble`

### 5.6 静的プロップ

#### Solid obstacle

データ:

- `half_extents_xz`
- `height`
- `solid = true`

描画:

- `draw_box()`
- y_offset: 0.0
- color: 5 if `kind == "obstacle"` else 4
- face colors:
  - top: `min(color+1, 15)`
  - north/south: `color`
  - east/west: `max(color-1, 1)`
- face outline color: 0

collision:

- AABB in X/Z.
- collision and visual rendering are separate paths.

#### Sprite prop / tree placeholder

データ:

- kind: `sprite_prop`
- `sprite_world_size`: 48.0 x 64.0
- collision half extents: 8.0 x 8.0
- height: 64.0
- `occludes_player = true`

描画:

- `sprite_prop_bounds()` でroot/topを投影し、screen rectを作る。
- foot/root anchor is bottom center of the screen rect.
- trunk: `rect` + `rectb`
- crown: three `circ`
- ground line: `line`

現行名はsprite_propだが、まだ実画像スプライトではない。

#### Water station

描画:

- projection anchor: object root
- working: color 12
- stopped: color 13
- screen fixed primitive: `rect(x-4, y-12, 8, 12)` and top line

World visual size:

- 明示的な `sprite_world_size` は未設定。
- visual cullingでは最低幅/高さが `object_visual_bounds()` で補われる。

#### Solar station

描画:

- root投影から `tri`。
- screen fixed primitive。
- color 10。

#### Ambient maintenance

描画:

- root投影から 10 x 12 px の `rect`/`rectb`。
- eye-like `pset` color 10。

#### Inspectable sign/post

描画:

- root投影から `rectb(x-5, y-13, 10, 12, 7)` と `pset`。

#### Reactive grass

描画:

- root投影から短い3本の `line`。
- phase は `(int(obj.x + obj.z) // 16) % 2`。

## 6. スプライトの拡縮・反転・画像領域

現行実装では、本番スプライトの概念はまだ未接続。

現在あるもの:

- `StaticObject.visual`: visual id文字列を保持しているが、描画分岐ではkind中心に処理している。
- `StaticObject.sprite_world_width`
- `StaticObject.sprite_world_height`
- `Renderer.sprite_prop_bounds()`: world sizeからscreen rectを算出できる。
- `WorldData.object_visual_bounds()`: visual culling用の保守的boundsを作る。

現在ないもの:

- 画像領域管理
- image bank割り当て
- `blt`描画
- colkey
- flip
- animation frame list
- HEX source loader
- HEX sourceとpacked imageの一致検証

スプライト拡縮:

- 現行のtree placeholderは、足元rootとtopの投影差から画面上の高さを得る。
- widthは `height * sprite_world_width / sprite_world_height`。
- minimum width/heightは 14/16 logical px。
- キャラクターはスプライトではなく3D box primitiveで、距離による自然投影。
- 敵はworld sizeからの投影ではなく `int(constant / depth)` の画面半径で近似。

反転:

- 現行実装には左右反転/上下反転はない。
- 進行方向に応じたsprite flipも未実装。

## 7. 深度ソートと遮蔽輪郭

### 7.1 DrawCommand

`DrawCommand` は以下を持つ。

- `depth`
- `layer_bias`
- `stable_id`
- `draw`

sort key:

```python
(-item.depth, item.layer_bias, item.stable_id)
```

意味:

- depthが大きいもの、つまり遠いものを先に描く。
- 同depthでは `layer_bias` が小さいものを先に描く。
- さらに `stable_id` で順序を安定化する。

現在のbias:

| 対象 | layer_bias |
|---|---:|
| bubble | -1 |
| static object | 0 |
| enemy | 0 |
| buddy | 0 |
| player | 0 |
| ground detail | 1 |

注意:

- playerを常に最前面にするbiasはない。
- buddyのbobやJackのhoverはsort depthへ入らない。
- `draw_box()` 内部では各面の平均depthで奥から手前へ描く。

### 7.2 遮蔽輪郭

Jackの遮蔽は簡易矩形判定。

条件:

1. `obj.occludes_player` がtrue。
2. occluderのrootがplayerより手前にある。
3. occluderのscreen rectとplayer screen rectが重なる。

成立時:

- コマンド描画後に `draw_player_outline()` を呼ぶ。
- player boundsの外側へ2重の `rectb` を描く。
- 色は外側7、内側12。

制約:

- ピクセル単位の葉抜き、半透明、穴判定はない。
- 遮蔽物の全画素マスクは使わない。
- 誤検出/過検出はあり得る。

関連:

- `Renderer.player_is_occluded`
- `Renderer.draw_player_outline`
- `Renderer.sprite_prop_bounds`

## 8. 可視範囲、衝突範囲、活動範囲

### 8.1 静的描画可視範囲

静的オブジェクトはchunk可視判定を経由する。

- chunk size: 128.0 world units
- world 1024 x 1024なので 8 x 8 = 64 chunks
- screen margin: 24.0 logical px
- visual max height: 96.0
- visual detail per chunk: 1

流れ:

1. `WorldData.query_visible_static_objects(camera, margin)`
2. 各chunkのworld AABBを投影。
3. viewport + margin と重なるchunkを候補化。
4. そのchunkのvisual indexからstatic object候補を得る。
5. `Renderer.object_is_visible()` でscreen boundsを再確認。

関連:

- `WorldData._build_visual_index`
- `WorldData.chunk_may_be_visible`
- `Renderer.object_is_visible`

### 8.2 ground detail

- 各chunkに安定seed由来の `GroundDetail` を生成。
- 描画対象chunkだけ `ground_details_for_chunks()` で抽出。
- 画面内margin判定後に描画。
- ゲーム判定には影響しない。

### 8.3 衝突範囲

衝突は可視カリングとは別。

- solid objectは `_solid_index` に登録。
- playerはAABB。
- enemyは円。
- queryはX/ZのAABB overlapでchunk indexから取得。

関連:

- `WorldData._build_solid_index`
- `WorldData.query_solids`
- `WorldData.move_player_sliding`
- `WorldData.move_enemy_circle_sliding`

### 8.4 敵活動範囲

敵更新のactive culling:

- active enter radius: 256.0
- active exit radius: 320.0
- stateが `IDLE` 以外ならpinされ、距離に関係なくactive。
- `DEFEATED` はactive対象外。

描画:

- `Renderer.world_commands()` は敵を全件見て、projectできるものを描画コマンド化する。
- active/dormantは更新負荷の制御であり、描画候補とは完全には一致しない。

関連:

- `GameModel.refresh_active_enemies`
- `Renderer.world_commands`

## 9. パレット、colkey、色置換

現行状態:

- Pyxel default palette indexを直接使用。
- custom palette loadはない。
- `pyxel.pal()` は使っていない。
- `colkey` は使っていない。
- `pyxel.blt()` は使っていない。
- 色置換、再減色、透明色変換は存在しない。

主な色indexの用途:

| 色index | 主な用途 |
|---:|---|
| 0 | shadow, outline dark |
| 1 | background clear |
| 2 | abnormal urchin base/dash ring |
| 3 | ground, some grass |
| 4 | tree trunk / non-obstacle solid fallback |
| 5 | obstacle body / return-home enemy / focus cue late |
| 7 | borders, markers, spikes, text |
| 8 | normal urchin / denied marker |
| 10 | buddy / solar / action marker |
| 11 | Jack / grid / grass |
| 12 | water, barrier, bubble, captured |
| 13 | stopped/rest/late cue |

HEXスプライト導入時の注意:

- HEX文字 `0` から `F` はPyxel palette indexに対応させる想定。
- 透明色を使う場合、colkey仕様をアセットメタデータに明示する必要がある。
- Codex側で色を補完、置換、再減色しない。
- 読み込み失敗時は明示し、既存の仮描画を維持する。

## 10. HEXスプライト導入時に再利用できる既存処理

再利用しやすいもの:

- `CameraState.project()`: world anchorをlogical pxへ投影。
- `DrawCommand`: depth sortとstable ordering。
- `Renderer.world_commands()`: static/dynamicを同じsort列へ入れる経路。
- `StaticObject.visual`: visual idの受け皿。
- `StaticObject.sprite_world_width`, `sprite_world_height`: world sizeの受け皿。
- `Renderer.sprite_prop_bounds()`: 足元root/top投影からscreen rectを得る処理。
- `WorldData.object_visual_bounds()`: 可視カリング用の保守的bounds。
- `WorldData.query_visible_static_objects()`: chunk単位の候補抽出。
- `Renderer.object_screen_bounds()`: 可視判定用screen rect。

新規に必要になるもの:

- HEX source parser。
- palette char validation (`0-9A-F`)。
- asset metadata schema。
- image bank packing。
- source HEXとpacked image pixelsの一致検証。
- frame/animation selection。
- sprite anchor adapter。
- colkey handling。
- flip handling。
- アセット読み込み失敗時の明示ログ/警告。

推奨するメタデータ項目:

```text
id
hex_width
hex_height
hex_rows
colkey
anchor_px
world_size
sort_anchor
visual_bounds
frames
frame_duration_sec
flip_policy
```

導入時の方針:

- アセット未提供時は現行仮描画を維持する。
- HEXから復元したプレビューだけを正とする。
- 変換・パッキング後も元HEXの各画素と一致することを自動検査する。
- 不一致や未定義文字はエラーとして扱い、推測補完しない。

## 11. 関連ファイル・クラス・関数

### 設定・データ

- `src/drift_with_me/data/game_config.json`
- `src/drift_with_me/data/prototype_world.json`
- `src/drift_with_me/config.py`
- `RuntimeConfig`
- `load_runtime_config`
- `load_world_data`

### ワールド・カリング

- `src/drift_with_me/world.py`
- `StaticObject`
- `GroundDetail`
- `StaticVisibilityQuery`
- `WorldData`
- `WorldData.object_visual_bounds`
- `WorldData.query_visible_static_objects`
- `WorldData.query_solids`
- `project_world_aabb`

### モデル

- `src/drift_with_me/model.py`
- `PlayerState`
- `BuddyState`
- `EnemyState`
- `BubbleState`
- `GameModel.refresh_active_enemies`
- `GameModel.enemy_radius`
- `GameModel.buddy_goal`

### カメラ・投影

- `src/drift_with_me/camera.py`
- `CameraController`
- `CameraShot`
- `CameraController.follow_shot`
- `CameraController.zone_shot`
- `CameraController.focus_shot`
- `CameraController.resolve_cue_shot`
- `src/drift_with_me/math3d.py`
- `CameraState`
- `CameraState.project`

### 描画

- `src/drift_with_me/render.py`
- `Renderer`
- `DrawCommand`
- `ScreenRect`
- `RenderStats`
- `Renderer.draw_scene`
- `Renderer.world_commands`
- `Renderer.draw_player`
- `Renderer.draw_buddy`
- `Renderer.draw_enemy`
- `Renderer.draw_bubble`
- `Renderer.draw_object`
- `Renderer.draw_sprite_prop`
- `Renderer.draw_box`
- `Renderer.sprite_prop_bounds`
- `Renderer.player_is_occluded`
- `Renderer.draw_player_outline`

### UI/Web

- `src/drift_with_me/app.py`
- `DriftWithMeApp`
- `DriftWithMeApp.draw_hud`
- `DriftWithMeApp.action_button_mode`
- `docs/host.css`
- `docs/host.js`
- `scripts/build_web.py`

## 12. スクリーンショット添付状況

本作業では、以下の参考画像は未添付。

- 通常カメラ
- overview
- focus
- 遮蔽物の後ろ

理由:

- 既存リポジトリには、任意のゲーム状態を作って名前付きスクリーンショットを保存する補助スクリプトがない。
- Pyxel 2.9.9に `screenshot` APIがあることは確認したが、簡易試行では作業ツリー内に画像ファイルは生成されなかった。
- 今回の範囲は読み取りと文書化であり、撮影用コードや状態固定用ハーネスの追加は行わない。

未確認:

- Pyxel headless環境での安定したスクリーンショット保存先。
- Web Canvasの実CSS表示px。
- iPhone実機の各状態における表示後px寸法。

次に画像添付を行う場合の候補:

- `scripts/capture_render_contract_screens.py` のような一時/正式スクリプトを作る。
- 状態を固定した `GameModel` と `CameraController` を用意する。
- normal/overview/focus/occlusionの4状態を同一解像度で保存する。
- 各画像には論理pxサイズと、Web/PCでの表示後pxを別記する。
