# JWP012B Jack Front/Back Sprites

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
|`jack_front_32`|`front_00`|0|`(0,32,32,32)`|`5cf48ead95a750c893f45e925bbe33d8deb5e778945e33e78fd74e4fc003cf6f`|
|`jack_back_32`|`back_00`|0|`(0,128,32,32)`|`19848ca6c4c3e4df4670ae62824943a054aed4fe56a3a57320aa605a3f67d7b6`|

`tilemaps`, `sounds`, and `musics` remain empty in this pyxres pack. The load options still exclude tilemaps, sounds, and musics.

## Source Art

- `src/drift_with_me/assets/jack_front_00.hex`
- `src/drift_with_me/assets/jack_back_00.hex`

These files preserve the delivered 32x32 palette-index pixels. The original diagonal `idle_00` source HEX is still not present in the repository.

## Direction Selection

- No movement yet: keep the previous/default `idle` view.
- Screen-down movement dominant: use `jack_front_32`.
- Screen-up movement dominant: use `jack_back_32`.
- Horizontal/diagonal movement dominant: use `jack_idle_32` with the existing left/right flip behavior.

The direction names describe the sprite view, not fixed world X/Z axes.

## Not Included

- Left/right dedicated sprites.
- Walking animation frames.
- Buddy, urchin, effect, prop, or ground asset changes.
- Pixel-perfect silhouette occlusion.
- Real-device iPhone validation.
