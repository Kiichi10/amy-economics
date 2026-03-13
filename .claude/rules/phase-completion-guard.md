# Phase完了ガード（自動発火ルール）

## 目的
Phase完了宣言前に、必ずWORKFLOW.mdのチェックリストを確認してから報告する。

## 発火トリガー
以下の文言をユーザーへの報告に含める直前に自動発火:
- 「Phase X 完了」
- 「〜が完了しました」
- 「次のPhaseに進みます」

## 発火時の行動

### 1. WORKFLOW.mdの該当Phaseを確認
```
WORKFLOW.md の Phase X セクションをReadする
```

### 2. チェック項目を1つずつ確認
- 各項目について、実際に完了しているか事実確認
- 未完了項目がある場合 → 完了宣言せず、残作業を実行

### 3. 全項目クリア後に報告

## Phase別の特別注意事項

### Phase 3 完了時
- Tinderレビュー（panel_mapping_reviewer.py --shorts）で全シーンがapprovedか
- scene_review.jsonはTinderレビューアが生成するもの。お頭が直接書き込まない

### Phase 4 完了時
- i2v対象シーンのmp4が配置済みか（i2v未配置でレンダリングしない）
- shorts_test.mp4の存在確認

### Phase 5 完了時
- upload_log.jsonにエントリが追加されているか
- YouTube APIで全動画のprivacy実態を確認し、upload_log.jsonと同期
- サムネはYouTubeアプリでユーザーがフレーム選択（お頭は作成しない）

### Phase 6 完了時
- upload_log.jsonのprivacy状態がYouTube APIの実態と一致しているか
- Gemini生成画像がarchive/にコピー済みか
- archive/index.jsonが作成済みか
- claude-brainバックアップ（git add/commit/push）済みか

## NG行動
- チェックリストを見ずに「完了」と報告する
- 一部未完了なのに「完了」と報告する
- WORKFLOW.mdをReadせずに記憶で完了判断する

---

**作成日**: 2026-03-12
