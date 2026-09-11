# JWP011C Jack pyxres Integration

作業開始HEAD: `3e6a72d223e505f0c71a1ea2fab6fe2903825221`

## 導入アセット

- runtime manifest: `src/drift_with_me/assets/jack_sprite.json`
- resource: `src/drift_with_me/assets/jack_sprite.pyxres`
- asset id: `jack_idle_32`
- frame id: `idle_00`
- image bank: `0`
- source rect: `(0, 0, 32, 32)`
- colkey: `0`
- anchor: `(16, 32)`
- world size: `(16.0, 16.0)`
- source pixel SHA-256: `9e63b51c48c928394fc992bda83c1c851588f69ba4dae7be7e340054d885cd7d`
- pyxres SHA-256: `102a53048ca8b74fe2c288bc55ba46f22c10ae05287e6455ee34c8fdae84a3d5`

## 実装内容

- 通常ゲーム実行では、Jack画像を事前焼き込み済み `.pyxres` から読み込む。
- `pyxel.load()` は初期化時に一度だけ実行し、画像だけを対象にする。
- tilemap、sound、musicは読み込み対象から除外する。
- `.pyxres` ロード後、指定フレーム領域の画素を読み戻し、metadataの `source_hash` と照合する。
- 既存のアンカー、拡縮、深度順、影、hover、衝突、入力、カメラは変更しない。
- 読み込み失敗時は `asset_error: ...` を一度出し、既存の仮図形描画へ戻す。

## 未確認

- iPhone実機での見た目と操作感。
- 実機Safari/PWAでの `.pyxres` 読み込み。
- ゲーム中のSE実再生の手動確認。
- FPS比較。
