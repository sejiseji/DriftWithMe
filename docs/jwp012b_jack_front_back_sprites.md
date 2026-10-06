# JWP012B Jack Front/Back Sprites

2026-09-13追記: `drift_with_me_jack_eight_directions_v0_2.zip` を取り込み、Jackは8方向静止スプライト選択へ拡張済み。既存のfront/back/idle画素、表示寸法、hover、影、collider、入力、カメラ、SEは変更していない。

## Scope

- Source pack: `drift_with_me_jack_front_back_v0_1.zip`
- Baseline HEAD before work: `9deeb83bb980f69e49efac1f745b453fcfd45147`
- Added only Jack static front/back sprites and direction selection.
- Gameplay, collision, hover, shadow, camera, input, SE, palette, and world size were not changed.

## Runtime Assets

The new pixels are baked into `src/drift_with_me/assets/jack_sprite.pyxres`.
The runtime manifest is `src/drift_with_me/assets/jack_sprite.json`.

|asset|frame|bank|rect|hash|
|---|---|---:|---|---|
|`jack_idle_32`|`idle_00`|0|`(0,0,32,32)`|`9e63b51c48c928394fc992bda83c1c851588f69ba4dae7be7e340054d885cd7d`|
|`jack_front_left_32`|`front_left_00`|0|`(0,0,32,32)`|`9e63b51c48c928394fc992bda83c1c851588f69ba4dae7be7e340054d885cd7d`|
|`jack_front_right_32`|`front_right_00`|0|`(32,0,32,32)`|`173a29c11bf5952a27e37a3a501a8ac5f941c9de0eb7e424238b30fca39784ab`|
|`jack_front_32`|`front_00`|0|`(0,32,32,32)`|`5cf48ead95a750c893f45e925bbe33d8deb5e778945e33e78fd74e4fc003cf6f`|
|`jack_left_32`|`left_00`|0|`(0,64,32,32)`|`ddeb02e3d1ff05281c9fb0ebfadf94c31ca7c66ff55ba5ac273ae68be160d419`|
|`jack_back_left_32`|`back_left_00`|0|`(32,64,32,32)`|`48d752c3ea5e5c4669306669cb7159953d637615e09d22edd58a9f30f171b5a0`|
|`jack_right_32`|`right_00`|0|`(0,96,32,32)`|`00792669416356148de3d10ec2320cf6013e94f71328aac9670319b02934dfd8`|
|`jack_back_right_32`|`back_right_00`|0|`(32,96,32,32)`|`c3f00558ffc3b6cf579e96cfd730e406501859602d26a3fb5b785f9b6c19d72a`|
|`jack_back_32`|`back_00`|0|`(0,128,32,32)`|`19848ca6c4c3e4df4670ae62824943a054aed4fe56a3a57320aa605a3f67d7b6`|

`tilemaps`, `sounds`, and `musics` remain empty in this pyxres pack. The load options still exclude tilemaps, sounds, and musics.

## Source Art

- `src/drift_with_me/assets/jack_front_00.hex`
- `src/drift_with_me/assets/jack_front_left_00.hex`
- `src/drift_with_me/assets/jack_front_right_00.hex`
- `src/drift_with_me/assets/jack_left_00.hex`
- `src/drift_with_me/assets/jack_right_00.hex`
- `src/drift_with_me/assets/jack_back_left_00.hex`
- `src/drift_with_me/assets/jack_back_00.hex`
- `src/drift_with_me/assets/jack_back_right_00.hex`

These files preserve the delivered 32x32 palette-index pixels. `jack_front_left_32` intentionally aliases the existing `jack_idle_32` frame at `(0,0)`.

## Direction Selection

- No movement yet: keep the previous/default `idle` view.
- Movement uses the last projected screen-space direction and selects one of `right`, `front_right`, `front`, `front_left`, `left`, `back_left`, `back`, `back_right`.
- If a direction-specific asset is missing, rendering falls back to `jack_idle_32`; this preserves the older partial-asset behavior.
- The new 8-direction runtime path does not mirror Jack when a baked direction exists.

The direction names describe the sprite view, not fixed world X/Z axes.

## Not Included

- Walking animation frames.
- Buddy, urchin, effect, prop, or ground asset changes.
- Pixel-perfect silhouette occlusion.
- Real-device iPhone validation.
