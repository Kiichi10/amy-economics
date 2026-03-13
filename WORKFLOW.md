# エイミー先生の経済学 — 動画制作ワークフロー

## 概要
1本の60秒Shorts動画を制作するフロー。2つのモードを持つ。

| モード | 概要 | 実行方法 |
|--------|------|----------|
| **Mode A**（対話型） | Phase単位で確認・調整。現在のメインモード | お頭に「モードAで」or 各Phaseを手動実行 |
| **Mode B**（一括） | テーマを渡すだけで自動進行。i2v生成時のみ中断 | `SKIP_REVIEW=1 python3 pipeline_shorts.py <台本.txt> <テーマ>` |

---

# Mode A（対話型）

## Phase 1: 台本・音声生成

### お頭の作業
1. テーマに基づき台本を作成（エイミー先生＋少年の掛け合い形式）
   - CTA（チャンネル登録誘導）を末尾に必ず含める
   - 独自の切り口・最新ファクトで構成（参考動画の転載にならない）
2. `script_parser.py` で台本をパース
3. `script_to_audio.py` でVOICEVOX音声を生成
   - エイミー先生: speaker_id=20, 少年: speaker_id=12
4. 成果物: `audio/` フォルダに `audio_manifest.json` + 各セグメントWAV

### ユーザーの作業
- 台本の内容を確認・修正指示
- 音声ナレーションの確認（読み方の間違い、イントネーション等）

---

## Phase 2: 素材生成（画像・パネル・i2v）

### ステップ順序

```
2-1. お頭: scenes.json作成（全シーンのasset_type=geminiで定義）
2-2. お頭: Gemini画像生成（全シーン、ref_image必須）+ Pillowパネル生成
2-3. お頭: i2v対象シーン（冒頭2-3枚）の英語プロンプトを提示
2-4. ユーザー: i2v動画をGrok等で生成 → お頭に.mp4パスを伝える
2-5. お頭: .mp4をassets/scenes/に配置 → scenes.jsonのassetパスを.mp4に変更
```

### お頭の作業
1. `scenes.json` を作成
   - 全シーンの asset_type は `gemini`、`pillow`、または `pixabay`（**`i2v`は使わない**）
   - i2vシーンも最初はPNGで生成し、後でassetパスだけ.mp4に変更する
   - 全Geminiシーンに `ref_image: "ref"` を必ず設定（16:9保証）
   - 全Geminiシーンに `has_main_character: true/false` を必ず設定（メインキャラ登場比率33-40%制御用。`gemini_image_gen.py`のpreflightで未設定シーンはエラー停止する）
2. Gemini画像生成（`gemini_image_gen.py`）
   - reference.png をリファレンスとして渡す（ref_image未設定は正方形になる）
3. Pillowパネル生成（`create_data_panels.py`）
   - 棒グラフ・円グラフ・VS比較など数値データのビジュアル化
4. **i2vプロンプト提示**: 冒頭の連続2-3シーンについて、**英語**プロンプトを生成してユーザーに渡す
   - 対象は必ず冒頭から連続するシーン（scene_01, scene_02, ...）
5. ユーザーのi2v動画(.mp4)を `assets/scenes/` に配置し、scenes.jsonのassetパスを `.png` → `.mp4` に変更
   - **asset_typeは変更しない**（geminiのまま）
   - render_shorts.pyが拡張子で自動的に動画として処理する
6. 成果物: `assets/scenes/` に画像+動画、`assets/panels/` にパネル

### ユーザーの作業
- **i2v動画の生成**（手動）
  - お頭が提示した英語プロンプト + 元の静止画を使ってGrok等でi2v生成
  - 生成した.mp4のパスをお頭に伝える（お頭が配置する）
  - Grok無料枠を優先。枠不足時: Kling 3.0 Standard (fal.ai, $0.145/5s) 等

---

## Phase 3: Tinderレビュー

### お頭の作業
1. Tinderレビューアを起動: `python3 scripts/panel_mapping_reviewer.py --shorts <scenes.json>`
   - **お頭はscene_review.jsonを直接書き込まない**（フックでブロック済み）
   - scene_review.jsonはレビューア（ブラウザUI）がユーザーの操作に基づいて生成する
2. レビューア完了をバックグラウンドで検知（exit code 0で自動検知、ユーザーに聞かない）
3. scene_review.jsonの内容を読み込み、次のPhaseに進む

### ユーザーの作業
- ブラウザでTinderレビューアを操作し、各シーンを確認
- Ken Burns設定、エフェクト、SEを調整
- 全シーンをapprove

---

## Phase 4: レンダリング

### お頭の作業
1. `generate_render_plan.py` で `render_plan.json` を生成
   - 字幕: max_chars=18（3行切捨て防止）、max_lines=2
   - パネル: Ken Burns自動無効
   - i2v動画: .mp4アセットは自動検出、動画フレーム再生
   - SEGMENT_GAP=0.3（音声・映像・scenes.jsonで統一）
2. `render_shorts.py` でレンダリング
   - preflight: 実フォントで字幕行数検証、アセット存在確認
   - 出力: 1080x1920 @ 30fps MP4
3. 成果物: `shorts_a_vX.mp4`

### ユーザーの作業
- 完成動画を確認
- 問題があれば修正指示（字幕タイミング、映像切替、SE調整等）

---

## Phase 5: YouTube公開準備

### お頭の作業
1. メタデータ生成（タイトル候補3つ、概要欄、タグ10-15個）
2. `youtube_uploader.py` でアップロード（private）
3. サムネイル案内: 「YouTubeアプリでフレーム選択してください」と伝えるだけ
   - **お頭はサムネイル画像を作成しない**（Shortsはアプリでフレーム選択のみ）

### ユーザーの作業
- タイトル最終決定
- 概要欄の確認・修正
- **YouTubeアプリでサムネイルのフレーム選択**（モバイルのみ可能）
- 公開タイミングの指示

---

## Phase 6: 公開・整理

### お頭の作業
1. YouTube動画を public に変更
2. upload_log.json を更新
   - **YouTube APIで全動画の実際のprivacy状態を確認**してからログを書く（推測で書き換えない）
3. Gemini生成画像を `archive/` にコピー + `index.json` 更新
4. claude-brainバックアップ: `cd ~/.claude && git add . && git commit && git push`

### ユーザーの作業
- YouTube上で公開確認
- SNS投稿（任意）

---

## ファイル構成（1テーマあたり）

```
samples/テーマ名/
├── 台本.txt              # 元台本
├── scenes.json           # シーン定義（タイミング・アセット・SE・エフェクト）
├── scene_review.json     # Tinderレビュー結果
├── render_plan_a.json    # レンダリング設計書
├── shorts_a_vX.mp4       # 完成動画
├── audio/
│   ├── audio_manifest.json
│   ├── segment_001_shonen.wav
│   ├── segment_002_amy_sensei.wav
│   └── ...
└── assets/
    ├── scenes/           # Gemini画像 + i2v動画(.mp4)
    └── panels/           # Pillowパネル（Ken Burns無効）
```

---

## 注意事項（過去の教訓）

| 問題 | 原因 | 対策 |
|------|------|------|
| 音声-映像ズレ | SEGMENT_GAP不一致 | 3箇所で0.3s統一。premixキャッシュ削除してから再レンダリング |
| 字幕が消える | split_subtitle max_chars大きすぎ | max_chars=18。preflightで実フォント検証 |
| パネルが動く | Ken Burns適用 | `/panels/`は自動でKen Burns無効 |
| i2v尺ミスマッチ | 静止画前提で尺設定 | Phase 2でi2v先行実行、scenes.jsonに6s尺で設定 |
| premix再利用 | 古いmixed_audio.wav残存 | GAP変更時は必ず削除 |

---

# Mode B（一括パイプライン）

## 実行方法
```bash
SKIP_REVIEW=1 python3 pipeline_shorts.py <台本.txt> <テーマ>
```

## Phase別の動作（Mode Aとの差分）

### Phase 1: 音声生成
- Mode Aと同一
- 50秒未満の場合: お頭が台本を自動加筆して再生成（ユーザー確認なし）

### Phase 2: 素材生成 + i2v中断ポイント
1. お頭がscenes.json一括作成 → Gemini/Pillow画像を連続生成
2. **i2v中断ポイント**: 画像生成完了後、パイプラインを一時停止
   - i2v対象シーン（冒頭2-3枚）のプロンプトをユーザーに提示
   - ユーザーがGrok等でi2v生成 → `assets/scenes/scene_XX.mp4` に配置
   - ユーザーが「配置した」と報告 → パイプライン再開
   - **将来**: API連携（Kling/Grok API）で自動化予定

### Phase 3: scene_review.json自動生成
Tinderレビューをスキップし、`generate_mode_b_scene_review()` で自動生成。

**SE自動配置ルール（7-8個/60秒動画）**:

| 条件 | SE種類 |
|------|--------|
| scene_01（オープニング） | `whoosh`（固定） |
| 最終scene（エンディング） | なし（固定） |
| `asset_type: "pillow"`（データパネル） | なし（視覚的に十分） |
| 経済危機系キーワード（暴落, 破綻, 崩壊, ショック, 危機） | `impact` |
| 驚き系キーワード（発覚, なんと, 実は, 驚, 意外） | `surprise` |
| 転換系キーワード（しかし, ところが, 一方, 転換, 逆に） | `whoosh` |

**FX自動配置ルール（2-3箇所）**:

| 条件 | FX種類 |
|------|--------|
| スコア≥3（クライマックス系） | `flash` |
| スコア≥2（衝撃系） | `shake` |
| scene_01 | 配置禁止 |

### Phase 4: レンダリング
- scene_review.json未作成時は自動生成にフォールバック
- Preflightチェックは全項目実行（字幕max_chars=18）
- ゲート不合格時はお頭が自動修復

### Phase 5-6: YouTube公開
- Mode Aと同一手順
- タイトルはユーザーが3候補から選択（自動決定禁止）

## ユーザー介入ポイントまとめ（Mode B）

| タイミング | ユーザーがやること |
|-----------|-----------------|
| Phase 2完了後 | **i2v動画の生成・配置** ← 唯一の中断ポイント |
| Phase 5 | タイトル選択（3候補から） |
| Phase 5完了後 | サムネイルのフレーム選択（モバイル） |

## 関連ファイル

| ファイル | 役割 |
|---------|------|
| `pipeline_shorts.py` | パイプライン本体（Phase 1-5実行、Mode B scene_review自動生成） |
| `render_shorts.py` | レンダリングエンジン + Preflightチェック |
| `scripts/script_to_audio.py` | VOICEVOX音声生成 |
| `scripts/generate_render_plan.py` | render_plan.json生成（BGM/SE/FX統合） |
| `scripts/gemini_image_gen.py` | Gemini Imagen画像生成 |
| `scripts/panel_mapping_reviewer.py` | Tinderレビュー（Mode Aのみ） |
| `scripts/youtube_uploader.py` | YouTubeアップロード・メタデータ更新 |
