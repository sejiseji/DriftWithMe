# Japanese UI v0.1 Integration Notes

## Scope

- Source design pack: `drift_jp_ui_v01.zip`
- Implemented JPUI-01: Japanese UI text resources and runtime font drawing.
- JPUI-02 side-HUD relayout, Safe Area measurement, and device CSS touch-size auditing remain separate follow-up work.

## Font

The runtime now bundles DotGothic16 for UI text.

|Item|Value|
|---|---|
|Font file|`src/drift_with_me/assets/fonts/DotGothic16-Regular.ttf`|
|License file|`docs/licenses/DotGothic16-OFL.txt`|
|License|SIL Open Font License 1.1|
|TTF SHA-256|`155da8f318553c11d9dffc2affbc7c2114c6a46f9740bcf639ed5568af92be71`|
|OFL SHA-256|`b6630c61ea078cacd7fabe37d14ffe557a0b45b06683374a9aa9e24262993e33`|

The font is loaded after `pyxel.init()` via `pyxel.Font`. If loading fails, the UI renderer falls back to the existing pixel-font path.

Source reference: https://github.com/fontworks-fonts/DotGothic16

## Text Resources

`src/drift_with_me/assets/i18n/ui_text.json` maps existing display tokens to localized text.

Important boundary:

- gameplay state IDs remain English tokens such as `BUBBLE`, `GUARD`, and `ZAP`
- input, collision, resources, camera, SE, sprites, and pyxres are unchanged
- denial display uses the existing reason payload instead of showing a translated `DENIED` prefix
- inspect body text is selected from the existing world `texts[<key>]["ja"]` entries at draw time

## Current UI Coverage

Japanese display now covers:

- main action button: 行動 / 待機 / 泡 / 防御 / 電撃
- context button: 調べる / 給水 / 充電
- resource HUD: 水 / 電力
- pause and sound buttons
- start screen primary labels
- interaction chip title, body, and 閉じる button
- action-denied reason text

The current physical button placement is mostly unchanged. The interaction chip close button was widened to fit Japanese text at high profile font size.

## Verification

Automated checks cover:

- localization resource lookup for existing tokens
- denial reason translation
- DotGothic16 runtime loading through Pyxel 2.9.9
- major label widths fitting existing button rectangles across low / medium / high profiles
- existing UI layout and pointer-capture regression tests

Manual device checks still needed:

- iPhone Safari and home-screen display
- both landscape orientations
- Canvas CSS size and 44x44 CSS px target-size measurement
- visual comparison of 16px versus 18px labels, and high profile 20px versus 22px
