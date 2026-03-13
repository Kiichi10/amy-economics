#!/usr/bin/env python3
"""
エイミー先生の経済学 — Shortsパイプライン

Mode A（対話型）: Phase単位で実行。ユーザーが各段階で確認・調整。
Mode B（一括）:   テーマを渡すだけで自動進行。i2v生成時のみ中断。

Phase 1: 台本 → VOICEVOX音声生成（掛け合い: エイミー先生+少年）
Phase 2: scenes.json作成 + 画像生成（Gemini/Pillow）+ i2v中断ポイント
Phase 3: Tinderレビュー（Mode A）/ scene_review.json自動生成（Mode B）
Phase 4: render_plan生成 + レンダリング
Phase 5: YouTubeアップロード（非公開）

使い方:
  # Mode A: Phase単位で実行
  python3 pipeline_shorts.py <台本.txt> <テーマ> --phase 1
  python3 pipeline_shorts.py <台本.txt> <テーマ> --phase 4
  python3 pipeline_shorts.py <台本.txt> <テーマ> --phase 5

  # Mode B: 一括実行（i2v中断あり）
  SKIP_REVIEW=1 python3 pipeline_shorts.py <台本.txt> <テーマ>

  # Mode B: i2v配置後の再開（Phase 3から続行）
  SKIP_REVIEW=1 python3 pipeline_shorts.py <台本.txt> <テーマ> --resume-after-i2v

例:
  python3 pipeline_shorts.py 台本.txt スタグフレーション --phase 1
  SKIP_REVIEW=1 python3 pipeline_shorts.py 台本.txt スタグフレーション
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SAMPLES_DIR = PROJECT_ROOT / "samples"

# 経済学固有の設定
SEGMENT_GAP = 0.3  # 音声セグメント間ギャップ（秒）
SUBTITLE_MAX_CHARS = 18  # 字幕最大文字数/行
I2V_SCENE_COUNT = 3  # i2v対象シーン数（冒頭）


def run(cmd, description, timeout=600):
    """コマンド実行"""
    print(f"\n{'='*60}")
    print(f"  {description}")
    print(f"{'='*60}")
    print(f"  $ {' '.join(str(c) for c in cmd)}\n")

    start = time.time()
    result = subprocess.run([str(c) for c in cmd], cwd=str(PROJECT_ROOT), timeout=timeout)
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n  FAIL (exit code {result.returncode}, {elapsed:.1f}s)")
        return False
    print(f"\n  OK ({elapsed:.1f}s)")
    return True


def generate_mode_b_scene_review(theme_dir: Path):
    """
    Mode B用: scenes.jsonからSE/FXを自動配置したscene_review.jsonを生成。

    経済学チャンネル向けにキーワードを調整:
      - 経済危機系: impact
      - 驚き・発覚系: surprise
      - 転換・展開系: whoosh
      - データパネル: SEなし

    SE: 7-8個/60秒動画、FX: 2-3箇所
    """
    scenes_path = theme_dir / "scenes.json"
    review_path = theme_dir / "scene_review.json"

    with open(scenes_path, "r", encoding="utf-8") as f:
        scenes_data = json.load(f)

    scenes = scenes_data["scenes"]
    total_scenes = len(scenes)

    # SE判定キーワード（経済学チャンネル向け）
    crisis_keywords = ["暴落", "破綻", "崩壊", "ショック", "危機", "パニック", "急落", "デフォルト"]
    surprise_keywords = ["発覚", "なんと", "実は", "驚", "意外", "まさか", "衝撃", "ダブルパンチ"]
    transition_keywords = ["しかし", "ところが", "一方", "転換", "逆に", "ここから", "だからこそ"]

    # 各シーンのSE/FX候補を判定
    se_candidates = {}
    for i, scene in enumerate(scenes):
        sid = scene["id"]
        desc = scene.get("description", "")
        text = scene.get("text", "")
        asset_type = scene.get("asset_type", "")
        combined = desc + " " + text

        se = None
        effects = {}

        if i == 0:
            se = "whoosh"
        elif i == total_scenes - 1:
            se = None
        elif asset_type == "pillow":
            se = None
        elif any(kw in combined for kw in crisis_keywords):
            se = "impact"
        elif any(kw in combined for kw in surprise_keywords):
            se = "surprise"
        elif any(kw in combined for kw in transition_keywords):
            se = "whoosh"

        se_candidates[sid] = {"se": se, "effects": effects, "score": 0}

        # スコア付け（FX配置用）
        if any(kw in combined for kw in crisis_keywords):
            se_candidates[sid]["score"] += 2
        if any(kw in combined for kw in surprise_keywords):
            se_candidates[sid]["score"] += 1
        if "クライマックス" in desc or "締め" in desc or "結論" in desc:
            se_candidates[sid]["score"] += 3

    # SE数を7-8個に調整
    se_count = sum(1 for v in se_candidates.values() if v["se"] is not None)
    target_se = min(8, max(7, int(total_scenes * 0.5)))

    if se_count < target_se:
        no_se = [(sid, v) for sid, v in se_candidates.items()
                 if v["se"] is None and sid != scenes[-1]["id"]]
        no_se.sort(key=lambda x: x[1]["score"], reverse=True)
        for sid, v in no_se[:target_se - se_count]:
            v["se"] = "whoosh"
    elif se_count > target_se:
        with_se = [(sid, v) for sid, v in se_candidates.items()
                   if v["se"] is not None and sid != scenes[0]["id"]]
        with_se.sort(key=lambda x: x[1]["score"])
        for sid, v in with_se[:se_count - target_se]:
            v["se"] = None

    # FX配置: スコア上位2-3箇所（scene_01はflash/shake禁止）
    scored = [(sid, v) for sid, v in se_candidates.items()
              if v["score"] > 0 and sid != scenes[0]["id"]]
    scored.sort(key=lambda x: x[1]["score"], reverse=True)

    for i, (sid, v) in enumerate(scored[:3]):
        if i == 0 and v["score"] >= 3:
            v["effects"]["flash"] = True
        if v["score"] >= 2:
            v["effects"]["shake"] = True

    # scene_review.json出力
    review = {}
    for scene in scenes:
        sid = scene["id"]
        candidate = se_candidates[sid]
        review[sid] = {
            "status": "ok",
            "approved": True,
            "note": "Mode B auto-approved",
            "se": candidate["se"],
            "effects": candidate["effects"]
        }

    with open(review_path, "w", encoding="utf-8") as f:
        json.dump(review, f, ensure_ascii=False, indent=2)

    se_final = sum(1 for v in review.values() if v["se"] is not None)
    fx_final = sum(1 for v in review.values() if v.get("effects"))
    print(f"  scene_review.json自動生成: SE {se_final}個, FX {fx_final}箇所")
    return True


def check_voicevox():
    """VOICEVOX起動確認"""
    try:
        req = urllib.request.Request("http://localhost:50021/version")
        with urllib.request.urlopen(req, timeout=5) as res:
            version = res.read().decode().strip('"')
            print(f"  VOICEVOX v{version} OK")
            return True
    except Exception:
        print("  VOICEVOX not running")
        print("  -> open /Applications/VOICEVOX.app")
        return False


def create_preview_audio(audio_dir):
    """preview_audio.mp3作成（全セグメント連結）"""
    manifest_path = audio_dir / "audio_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    wav_files = []
    for seg in manifest["segments"]:
        wav_path = audio_dir / seg["file"]
        if wav_path.exists():
            wav_files.append(str(wav_path.resolve()))

    if not wav_files:
        print("  No WAV files found")
        return False

    preview_path = audio_dir / "preview_audio.mp3"
    concat_list = audio_dir / "concat_list.txt"
    with open(concat_list, "w") as f:
        for wf in wav_files:
            f.write(f"file '{wf}'\n")

    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-ar", "48000", "-ac", "1",
        str(preview_path)
    ], capture_output=True)
    concat_list.unlink(missing_ok=True)

    if result.returncode == 0:
        print(f"  preview_audio.mp3 created")
        return True
    print(f"  preview_audio.mp3 failed")
    return False


def create_mixed_audio(audio_dir):
    """音声セグメントからmixed_audio.aacを生成（タイミング保持）"""
    manifest_path = audio_dir / "audio_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    segments = manifest.get("segments", [])
    if not segments:
        return False

    total_dur = sum(s["duration"] for s in segments) + (len(segments) - 1) * SEGMENT_GAP
    gap_samples = int(SEGMENT_GAP * 48000)

    inputs = []
    filter_parts = []
    concat_labels = []
    for seg in segments:
        wav = audio_dir / seg["file"]
        if not wav.exists():
            continue
        idx = len(inputs) // 2
        inputs.extend(['-i', str(wav)])
        seg_label = f's{idx}'
        gap_label = f'g{idx}'
        filter_parts.append(f'[{idx}]aresample=48000[{seg_label}]')
        concat_labels.append(f'[{seg_label}]')
        filter_parts.append(f'aevalsrc=0:d={SEGMENT_GAP}:s=48000[{gap_label}]')
        concat_labels.append(f'[{gap_label}]')

    if not concat_labels:
        return False

    all_labels = ''.join(concat_labels)
    n = len(concat_labels)
    fc = ';'.join(filter_parts) + f';{all_labels}concat=n={n}:v=0:a=1[out]'
    output_path = audio_dir.parent / "mixed_audio.aac"

    cmd = ['ffmpeg', '-y'] + inputs + [
        '-filter_complex', fc, '-map', '[out]',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  mixed_audio.aac failed: {result.stderr[-200:]}")
        return False
    print(f"  mixed_audio.aac created ({total_dur:.1f}s)")
    return True


def checkpoint(message):
    """ユーザーチェックポイント"""
    print(f"\n{'*'*60}")
    print(f"  CHECKPOINT: {message}")
    print(f"{'*'*60}")
    response = input("  続行? (y/n): ").strip().lower()
    if response != 'y':
        print("  中断しました。")
        sys.exit(0)


def i2v_checkpoint(theme_dir):
    """
    Mode B i2v中断ポイント。
    画像生成完了後にユーザーにi2vプロンプトを提示し、配置を待つ。
    --resume-after-i2v で再開。
    """
    scenes_path = theme_dir / "scenes.json"
    if not scenes_path.exists():
        return

    with open(scenes_path, "r", encoding="utf-8") as f:
        scenes_data = json.load(f)

    # i2v対象シーンを特定
    i2v_scenes = [s for s in scenes_data["scenes"]
                  if s.get("asset_type") == "i2v"]

    if not i2v_scenes:
        print("  i2v対象シーンなし。Phase 3へ進行。")
        return

    print(f"\n{'*'*60}")
    print(f"  I2V中断ポイント: {len(i2v_scenes)}シーンのi2v動画が必要です")
    print(f"{'*'*60}")

    for scene in i2v_scenes:
        sid = scene["id"]
        desc = scene.get("description", "")
        source_img = theme_dir / "assets" / "scenes" / f"{sid}.png"
        target_mp4 = theme_dir / "assets" / "scenes" / f"{sid}.mp4"

        print(f"\n  [{sid}] {desc}")
        print(f"    元画像: {source_img}")
        print(f"    配置先: {target_mp4}")
        if scene.get("i2v_prompt"):
            print(f"    プロンプト: {scene['i2v_prompt']}")

    print(f"\n  i2v動画を生成して配置後、以下のコマンドで再開:")
    print(f"  SKIP_REVIEW=1 python3 pipeline_shorts.py <台本.txt> {theme_dir.name} --resume-after-i2v")
    print(f"\n  中断します。")
    sys.exit(0)


# ============================================================
# Phase 1: 音声生成
# ============================================================
def phase1(script_path, theme_dir):
    """台本 → VOICEVOX音声生成（掛け合い: エイミー先生+少年）"""
    print("\n" + "="*60)
    print("  Phase 1: 音声生成（エイミー先生 + 少年）")
    print("="*60)

    if not check_voicevox():
        return False

    audio_dir = theme_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    ok = run(
        ["python3", SCRIPTS_DIR / "script_to_audio.py", script_path, audio_dir],
        "VOICEVOX音声生成（掛け合い）",
        timeout=1200,
    )
    if not ok:
        return False

    create_preview_audio(audio_dir)
    create_mixed_audio(audio_dir)

    # 台本をテーマフォルダにコピー
    dest = theme_dir / script_path.name
    if not dest.exists():
        import shutil
        shutil.copy2(script_path, dest)
        print(f"  Script copied to {dest}")

    manifest_path = audio_dir / "audio_manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    seg_count = len(manifest["segments"])
    total_dur = manifest.get("total_duration", 0)
    print(f"\n  Result: {seg_count} segments, {total_dur:.1f}s")
    print(f"  Preview: {audio_dir / 'preview_audio.mp3'}")

    if total_dur < 50:
        print(f"\n  WARNING: 音声合計が{total_dur:.1f}秒です（推奨: 50秒以上）。台本の追加を検討してください。")

    return True


# ============================================================
# Phase 4: render_plan生成 + レンダリング
# ============================================================
def phase4(theme_dir):
    """render_plan生成 → レンダリング"""
    print("\n" + "="*60)
    print("  Phase 4: render_plan生成 + レンダリング")
    print("="*60)

    # ゲート: preview_audio.mp3
    preview_audio = theme_dir / "audio" / "preview_audio.mp3"
    if not preview_audio.exists():
        print(f"\n  ERROR: preview_audio.mp3が存在しません。Phase 1を先に実行してください。")
        return False

    # ゲート: scenes.json
    scenes_path = theme_dir / "scenes.json"
    if not scenes_path.exists():
        print(f"  ERROR: scenes.json not found. Phase 2を先に実行してください。")
        return False

    # ゲート: i2v動画の存在確認
    with open(scenes_path, "r", encoding="utf-8") as f:
        scenes_data = json.load(f)
    i2v_scenes = [s for s in scenes_data["scenes"] if s.get("asset_type") == "i2v"]
    for scene in i2v_scenes:
        mp4_path = theme_dir / "assets" / "scenes" / f"{scene['id']}.mp4"
        if not mp4_path.exists():
            print(f"  ERROR: i2v動画が未配置: {mp4_path}")
            print(f"  i2v動画を配置してから再実行してください。")
            return False

    # scene_review.json: 未作成ならMode B自動生成
    review_path = theme_dir / "scene_review.json"
    skip_review = os.environ.get("SKIP_REVIEW", "0") == "1"

    if not review_path.exists():
        print("  scene_review.json未検出 → Mode B自動生成（SE/FX自動配置）")
        generate_mode_b_scene_review(theme_dir)
    else:
        with open(review_path, "r", encoding="utf-8") as f:
            existing_review = json.load(f)
        has_se = any(v.get("se") for v in existing_review.values())
        if not has_se:
            print("  SE/FX未設定のscene_review.jsonを検出 → 再生成")
            generate_mode_b_scene_review(theme_dir)

    # mixed_audio.aac
    mixed_audio = theme_dir / "mixed_audio.aac"
    if not mixed_audio.exists():
        print("  mixed_audio.aac not found. Generating...")
        create_mixed_audio(theme_dir / "audio")

    # mixed_audio.aac実尺チェック
    if mixed_audio.exists():
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1", str(mixed_audio)],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                actual_dur = float(result.stdout.strip().split("=")[1])
                print(f"  mixed_audio.aac実尺: {actual_dur:.1f}秒")
                if actual_dur < 50.0:
                    print(f"  ERROR: 実尺が50秒未満 ({actual_dur:.1f}s) → 台本を加筆してPhase 1を再実行してください")
                    return False
        except Exception:
            pass

    # render_plan.json生成
    rel_theme = theme_dir.relative_to(PROJECT_ROOT)
    ok = run(
        ["python3", SCRIPTS_DIR / "generate_render_plan.py", str(rel_theme)],
        "render_plan.json生成（SE/BGM反映）",
    )
    if not ok:
        return False

    # レンダリング
    render_plan = theme_dir / "render_plan.json"
    output_file = theme_dir / "shorts.mp4"
    ok = run(
        ["python3", PROJECT_ROOT / "render_shorts.py", str(render_plan),
         "-o", str(output_file)],
        "Shorts動画レンダリング",
        timeout=1800,
    )
    if not ok:
        return False

    if output_file.exists():
        size_mb = output_file.stat().st_size / (1024 * 1024)
        print(f"\n  Output: {output_file} ({size_mb:.1f}MB)")

    return True


# ============================================================
# Phase 5: YouTubeアップロード（非公開）
# ============================================================
def phase5(theme_dir, title=None):
    """YouTube非公開アップロード"""
    print("\n" + "="*60)
    print("  Phase 5: YouTubeアップロード（API）")
    print("="*60)

    video_file = theme_dir / "shorts.mp4"
    if not video_file.exists():
        print(f"  ERROR: shorts.mp4 not found: {video_file}")
        return False

    scenes_path = theme_dir / "scenes.json"
    if not title and scenes_path.exists():
        with open(scenes_path, "r", encoding="utf-8") as f:
            scenes_data = json.load(f)
        title = scenes_data.get("meta", {}).get("topic", theme_dir.name)

    if not title:
        title = theme_dir.name

    shorts_title = f"{title} #Shorts"
    if len(shorts_title) > 100:
        shorts_title = shorts_title[:97] + "..."

    cmd = [
        "python3", SCRIPTS_DIR / "youtube_uploader.py",
        "--video", str(video_file),
        "--title", shorts_title,
        "--channel", "economics",
        "--shorts",
    ]

    ok = run(cmd, f"YouTube Upload: {shorts_title}", timeout=300)
    return ok


# ============================================================
# Main
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="エイミー先生の経済学 Shorts Pipeline")
    parser.add_argument("script", help="台本ファイル (.txt/.md)")
    parser.add_argument("theme", help="テーマフォルダ名 (samples/配下)")
    parser.add_argument("--phase", type=int, default=None,
                        help="実行するPhase (1/4/5)。省略時は全Phase。")
    parser.add_argument("--title", type=str, default=None,
                        help="YouTube動画タイトル")
    parser.add_argument("--resume-after-i2v", action="store_true",
                        help="i2v配置完了後の再開（Phase 3から続行）")
    args = parser.parse_args()

    script_path = Path(args.script)
    theme_dir = SAMPLES_DIR / args.theme
    theme_dir.mkdir(parents=True, exist_ok=True)

    phase = args.phase
    skip_review = os.environ.get("SKIP_REVIEW", "0") == "1"
    mode = "B（一括）" if skip_review else "A（対話型）"

    print(f"""
+----------------------------------------------------------+
|  エイミー先生の経済学 — Shortsパイプライン                   |
+----------------------------------------------------------+
|  台本:     {str(script_path):<46s}|
|  テーマ:   {args.theme:<46s}|
|  Phase:    {str(phase) if phase else '全Phase':<46s}|
|  モード:   {mode:<46s}|
+----------------------------------------------------------+
""")

    pipeline_start = time.time()

    # --resume-after-i2v: Phase 3から再開
    if args.resume_after_i2v:
        print("  i2v配置完了 → Phase 3から再開")
        # Phase 3
        if skip_review:
            review_path = theme_dir / "scene_review.json"
            if not review_path.exists():
                generate_mode_b_scene_review(theme_dir)
        # Phase 4
        if not phase4(theme_dir):
            sys.exit(1)
        if not skip_review:
            checkpoint("Phase 4完了。shorts.mp4を確認してください。")
        # Phase 5
        if not phase5(theme_dir, title=args.title):
            sys.exit(1)
        sys.exit(0)

    # Phase 1
    if phase is None or phase == 1:
        if not script_path.exists():
            print(f"  ERROR: Script not found: {script_path}")
            sys.exit(1)
        if not phase1(script_path, theme_dir):
            sys.exit(1)

        if phase is None and not skip_review:
            checkpoint(
                "Phase 1完了。preview_audio.mp3を確認してください。\n"
                "  Phase 2: scenes.json作成 + 画像生成を手動で実行してください。"
            )
        elif phase is None and skip_review:
            print("\n  Mode B: Phase 1完了 → Phase 2（画像生成）はお頭が対話で実施します。")
            print("  画像生成完了後、i2v中断ポイントで停止します。")

    # Phase 4
    if phase is None or phase == 4:
        if not phase4(theme_dir):
            sys.exit(1)

        if phase is None and not skip_review:
            checkpoint(
                "Phase 4完了。shorts.mp4を確認してください。\n"
                "  問題なければPhase 5（YouTubeアップロード）に進みます。"
            )

    # Phase 5
    if phase is None or phase == 5:
        if not phase5(theme_dir, title=args.title):
            sys.exit(1)

    # Summary
    total_time = time.time() - pipeline_start
    minutes = int(total_time // 60)
    seconds = int(total_time % 60)

    print(f"""
+----------------------------------------------------------+
|  パイプライン完了                                          |
+----------------------------------------------------------+
|  所要時間: {minutes}分{seconds}秒{' '*(43-len(str(minutes))-len(str(seconds)))}|
|  出力先:   {str(theme_dir):<46s}|
+----------------------------------------------------------+
""")


if __name__ == "__main__":
    main()
