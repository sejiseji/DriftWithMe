# JWP012A Buddy Sprite Hook

作業開始HEAD: `1c9ae0aabdc506d76d419865ed703e1433e34d65`

## 実装内容

- `assets.buddy_idle_asset` を追加した。
- 値が空文字の場合、buddyは従来どおり立方体の仮描画を使う。
- 値が有効なアセットIDの場合、Jackと同じpyxres/metadata経路、投影、アンカー、拡縮アダプターでbuddyを描画する。
- buddyの追従、sort基準、影、bob、衝突なしの扱いは変更しない。

## 未実装

- buddy本番アセットの同梱。
- buddy専用アニメーション、左右反転、感情差分。
- buddy画像を前提にした当たり判定やカメラ調整。
