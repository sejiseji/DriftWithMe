# WTR_LOOK04 + sparkle第6層 Production Asset Spec v0.1

## 目的
承認済み WTR_LOOK04 の水面モーション方向性を維持しつつ、最上位にゲーム表現寄りの sparkle 第6層を加えた production source を固定する。

## ソースの性質
- deep〜highlights の 5 層は LOOK04 motion study のプレビュー正本をそのまま Pyxel ソース化。
- sparkle は承認済み「水面用きらめきピクセルオーバーレイ」を基準に、1024x512 へ整形し、コンポーネント単位の位相ずらしで 24f ループ化した追加層。

## 技術仕様
- 画面論理サイズ: 1024x512
- 物理 chunk: 256x256 / 4x2
- フレーム数: 24
- 速度: 12fps 想定
- palette: Pyxel fixed 16 colors
- 透明: deep を除き colkey=8

## 出力物
- full_hex/*.hex.txt
- chunks_256/hex/*.hex.txt
- pyxel_png/<layer>/*.png
- production_manifest.json
- previews/*.gif *.mp4 *.png
