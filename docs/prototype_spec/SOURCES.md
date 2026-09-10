# 外部仕様の確認資料

確認日：2026-09-10。以下は公式資料。`main` の資料は将来更新されるため、実装時は**採用版の資料・型定義・実行挙動**も確認する。資料の確認は、このゲームの動作／実機性能の検証ではない。

| ID | 資料 | 本仕様で確認に使った点 |
|---|---|---|
| S1 | Pyxel公式の公開型定義 | init/run、入力、Font、bltの一様scale/rotate、Sound/再生APIの存在と形 |
| S2 | Pyxel User Guide | 16色・基本4音、package/app2html、実行構造 |
| S3 | Apple iPhone 16 Tech Specs | 公称ディスプレイ解像度2556×1179。CSS viewport寸法の根拠にはしない |
| S4 | WebKit: Designing Websites for iPhone X | viewport-fit=cover、Safe Area Insetsによる表示域とUIの保護 |
| S5 | WebKit Features in Safari 26.0 | ホーム画面からWebアプリとして起動する動作。通常タブのUI消去とは別 |
| S6 | W3C Pointer Events | pointer capture/cancel、touch-action、複数ポインターと互換入力の扱い |
| S7 | How to Use Pyxel for Web | app2html、Custom Elements、版固定、仮想ゲームパッド、pyxel-screen |

## 参照先

S1 — `https://raw.githubusercontent.com/kitao/pyxel/main/python/pyxel/__init__.pyi`

S2 — `https://raw.githubusercontent.com/kitao/pyxel/main/docs/user-guide.md`

S3 — `https://support.apple.com/en-us/121029`

S4 — `https://webkit.org/blog/7929/designing-websites-for-iphone-x/`

S5 — `https://webkit.org/blog/17333/webkit-features-in-safari-26-0/`

S6 — `https://www.w3.org/TR/pointerevents3/`

S7 — `https://raw.githubusercontent.com/kitao/pyxel/main/docs/web-usage.md`

## 実装前に追加で確認すること

Pyxelの採用版、デスクトップとWebのバージョン対応、既存Riversideの実装、JSとゲーム間の実際の情報受け渡し、iPhoneでのCanvasサイズ・Safe Area・中断復帰・音声開始はJWP000/002で確認する。

本書の世界観は創作設定であり、現生のメンダコが陸上で生存することや、泡と電撃の実際の物理効果を主張する資料ではない。ゲーム内の捕獲・電撃は仕様上のルールとして実装する。
