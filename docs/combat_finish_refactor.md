# Counter finishと戦闘復帰の限定整理

7月第1週の基準は `2d40bea`。目標UI・初回遭遇・Webホスト等の別作業は未コミットのまま保全しました。

`GameModel.combat_counter_finisher` が、集中（既存の消費0）と放電（既存counter energy cost）を選択し、可否表示と実行で同じ判断を使います。この照会は資源やphaseを変更しません。入力phaseとbubble_used/zap_usedの一度だけ実行するガード、実際の消費場所、演出開始とevent payloadは維持しました。

`apply_combat_enemy_outcome` は復帰時の敵状態だけを適用します。defeatはDEFEATED、captureはCAPTURED、それ以外の離脱はRESTです。ここでは資源消費・撃破イベント・演出開始を行いません。捕縛／離脱を撃破の報告へ変換する処理も追加していません。

比較：通常／異常ウニと通常／異常ウミウシ、資源不足／十分、反復入力の24条件で、資源・phase・結果・イベント・July保存文字列が変更前後で完全一致。会話等13枚と既存対応カメラの戦闘4枚も画素一致。Mac Chromeで会話切替、同じ保存データの再開、確認未完でマップ復帰／完了時帰庁、集中演出と消費0、通常セーブ非変更を比較しました。

新規回帰テスト `tests/test_combat_finish_contract.py` は連打、表示照会、資源不足、通常放電、無料集中、捕縛／離脱を実phase machineで検証します。整理版は作業ツリー1171テストとcheck_all PASSです。

別件として、従来の集中開始がAffineCameraStateをPerspective専用のcamera_ground_axesへ渡す例外を発見しました。整理前にも再現するため、互換修正はこの整理から独立させます。
