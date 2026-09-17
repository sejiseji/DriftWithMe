# CODEX IMPORT — SF HUD approved direct Pyxel v0.1

このパックは承認済みSF HUD画像からの直接抽出版です。
画像を見て再描画・再解釈しないでください。

正本:
- `assets_src/*.hex`
- `sf_ui_assets.py`
- `manifest.json`

## Integration
UIC001〜003で確定した情報構造・表示条件・hit rectは維持してください。
このパックは **visual skin / ornamental layer** として利用します。

推奨マッピング:
- resource panel → `sf_frame_resource`
- context status slot → `sf_frame_status_wide`
- sound → `sf_button_sound`
- pause → `sf_button_pause`
- primary action → `sf_button_primary`
- secondary action → `sf_button_secondary`
- minimap → `sf_minimap_shell`
- wordmark → `sf_wordmark_plate`
- build label → `sf_build_label_frame`

飾り罫類は必要箇所だけ任意配置。
hit rectやUI input precedenceを装飾に合わせて縮小しないでください。
