# WTR_LOOK04_Plus_Sparkle_Production_Assetization_v0.1

WTR_LOOK04 の 5 層構成に、ゲーム表現寄りの sparkle 第6層を追加した production asset パックです。

## 内容
- 6層・24フレーム・12fps の Water Study 本番ソース
- 各層の 1024x512 論理キャンバス HEX 正本
- 256x256 / 4x2 chunk 分割 HEX
- Pyxel パレット準拠 PNG 検査用ソース
- 再構成プレビュー GIF / MP4 / コンタクトシート
- Codex 接続用 manifest / handoff / 仕様書

## 層構成
1. water_deep_plane_e
2. water_mid_plane_e
3. water_surface_plane_e
4. water_surface_caustics_plane_e
5. water_highlights_plane_e
6. water_sparkle_plane_e

## ルール
- deep は不透明
- それ以外の5層は透過 `colkey=8` 前提
- deep〜highlights は LOOK04 motion study を基準に固定
- sparkle 第6層のみ今回追加生成
- Codex 側で再生成・再減色・再描画して完成扱いにしないこと
