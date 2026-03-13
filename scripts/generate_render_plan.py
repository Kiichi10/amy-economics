#!/usr/bin/env python3
"""
render_plan.json自動生成スクリプト

scenes.json + scene_review.json + audio_manifest.json → render_plan.json

Tinderレビューアで設定したFX/KB/SEの情報を反映してrender_plan.jsonを生成。

使い方:
  python3 scripts/generate_render_plan.py <テーマフォルダ>
  python3 scripts/generate_render_plan.py 中革連ブーメラン
"""

import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# SE type → MP3 file mapping
SE_MAP = {
    # トランジション系
    "whoosh": "assets/se/swipe1.mp3",
    "whoosh2": "assets/se/swipe2.mp3",
    "transition": "assets/se/transition_light.mp3",
    "scene_change": "assets/se/scene_change1.mp3",
    "scene_change2": "assets/se/scene_change2.mp3",
    # インパクト系
    "impact": "assets/se/shock.mp3",
    "impact2": "assets/se/shock_alt.mp3",
    "impact3": "assets/se/shock_alt2.mp3",
    "emphasis": "assets/se/emphasis_heavy1.mp3",
    "emphasis2": "assets/se/emphasis_heavy2.mp3",
    # リアクション系
    "surprise": "assets/se/驚く.mp3",
    "tension": "assets/se/heartbeat.mp3",
    "thinking": "assets/se/thinking.mp3",
    "question": "assets/se/question.mp3",
    "sad": "assets/se/sad.mp3",
    # ポジティブ系
    "correct": "assets/se/correct.mp3",
    "idea": "assets/se/idea.mp3",
    "idea_flash": "assets/se/idea_flash.mp3",
    "cheers": "assets/se/positive_cheers.mp3",
    "decision": "assets/se/decision.mp3",
    # ネガティブ系
    "incorrect": "assets/se/incorrect.mp3",
    "negative": "assets/se/negative_fall.mp3",
    # UI系
    "click": "assets/se/click_light.mp3",
    "button": "assets/se/button_light1.mp3",
    "title": "assets/se/title_appear.mp3",
    "clap": "assets/se/clap_wood.mp3",
}

# BGM category → (MP3 file, volume) mapping
# 音量はVOICEVOX音声との実地テストで確定（2026-03-11）
# 注: 全BGMはloudnorm=-16 LUFSに正規化してからvolumeを適用する想定
BGM_MAP = {
    "dramatic": "assets/bgm/bgm_dramatic_march.mp3",  # ドラマチック・マーチ（ブラス+ドラム）
    "news": "assets/bgm/bgm_news_tech.mp3",            # テクノ・未来感アンダースコア
    "pop": "assets/bgm/bgm_future_pop.mp3",            # エレクトロニカ・ポップ
}
BGM_VOLUME_MAP = {
    "dramatic": 0.08,
    "news": 0.08,
    "pop": 0.06,
}
BGM_VOLUME_DEFAULT = 0.08


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def split_subtitle(text, max_chars=18, _depth=0):
    """長いテキストを自然な区切りで分割（句読点・助詞で分割）

    ルール:
    - 「」引用文の途中では分割しない
    - 句読点（、。？！）の直後が最優先の分割点
    - 」の直後で分割するが、次が「で始まる場合は分割しない（引用の連続）
    - 末尾の句読点（。？！）は除去してから処理
    """
    # 末尾句読点を除去（折り返し時の孤立防止）
    text = text.rstrip('。？！?!')

    if len(text) <= max_chars:
        return [text]

    # 再帰深度ガード
    if _depth > 5:
        mid = len(text) // 2
        return [text[:mid], text[mid:]]

    # 引用文「〜」の範囲を特定（この範囲内では分割しない）
    quote_ranges = []
    depth = 0
    quote_start = -1
    for i, ch in enumerate(text):
        if ch == '「':
            if depth == 0:
                quote_start = i
            depth += 1
        elif ch == '」':
            depth -= 1
            if depth <= 0:
                depth = 0
                if quote_start >= 0:
                    quote_ranges.append((quote_start, i))
                quote_start = -1

    def in_quote(pos):
        """posが引用文の途中（開始「と終了」の間）にあるかチェック"""
        for qs, qe in quote_ranges:
            if qs < pos < qe:  # 「の直後〜」の直前は分割禁止
                return True
        return False

    # 分割候補点を収集（引用文内部は除外）
    split_points = []
    for i, ch in enumerate(text):
        pos = i + 1  # 分割はこの文字の直後
        if pos >= len(text):
            continue

        # 引用文内部は分割禁止
        if in_quote(pos):
            continue

        # 」の直後で次が「の場合は分割しない（引用の連続）
        if ch == '」' and pos < len(text) and text[pos] == '「':
            continue

        # 句読点・閉じ括弧の直後は分割候補
        if ch in '、。？！?!」）':
            split_points.append(pos)

    # 助詞の直後もフォールバック分割候補（split_pointsがない場合のみではなく常に収集）
    particle_points = []
    half = len(text) // 2
    for i in range(len(text) - 1, max(half - 1, 0), -1):
        if not in_quote(i + 1) and text[i] in 'はがをにでともへやかの':
            particle_points.append(i + 1)

    candidates = split_points or particle_points

    if not candidates:
        # どこにも分割点がない場合は文字数で分割
        mid = len(text) // 2
        return [text[:mid], text[mid:]]

    # max_chars以内で最適な分割点を見つける
    best = None
    for sp in candidates:
        if sp <= max_chars and (len(text) - sp) <= max_chars:
            best = sp
    if best is None:
        # 完璧な分割点がない場合、中央に最も近い分割点を使用
        mid = len(text) // 2
        best = min(candidates, key=lambda x: abs(x - mid))

    parts = [text[:best], text[best:]]
    # 再帰的に分割
    result = []
    for p in parts:
        if len(p) > max_chars:
            result.extend(split_subtitle(p, max_chars, _depth + 1))
        else:
            result.append(p)
    return result


def generate_render_plan(theme_dir, skip_review=False):
    """render_plan.jsonを生成"""
    theme_path = PROJECT_ROOT / theme_dir
    scenes_path = theme_path / "scenes.json"
    review_path = theme_path / "scene_review.json"
    manifest_path = theme_path / "audio" / "audio_manifest.json"

    if not scenes_path.exists():
        print(f"Error: {scenes_path} not found")
        return False

    scenes_data = load_json(scenes_path)
    scenes = scenes_data["scenes"]
    meta = scenes_data.get("meta", {})

    # Load review if exists
    reviews = {}
    if review_path.exists():
        reviews = load_json(review_path)

    # Load audio manifest for sentence timings
    # offsetはセグメント内相対値なので、セグメント累積開始時間を加算する
    # SEGMENT_GAPはscenes.jsonの生成時と_premix_voice()で同一値を使う
    SEGMENT_GAP = 0.3
    sentence_timings = []
    segments = []
    seg_timing = []  # (start, end) for each segment
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        segments = manifest.get("segments", [])
        seg_start = 0.0
        for seg in segments:
            seg_end = seg_start + seg["duration"]
            seg_timing.append((round(seg_start, 6), round(seg_end, 6)))
            for st in seg.get("sentence_timings", []):
                sentence_timings.append({
                    "text": st["text"],
                    "duration": st["duration"],
                    "offset": round(seg_start + st["offset"], 6)
                })
            seg_start = seg_end + SEGMENT_GAP

    # total_durationはpremix音声の実尺を使用
    if segments:
        total_duration = sum(seg["duration"] for seg in segments) + SEGMENT_GAP * (len(segments) - 1)
    else:
        total_duration = meta.get("total_duration", 0)
        if not total_duration and scenes:
            total_duration = max(s.get("end", 0) for s in scenes)

    # --- scenes.jsonのstart/endをaudio_manifestのタイミングに補正 ---
    # scenes.jsonのstart/endは生成時のタイミング計算に依存するため、
    # audio_manifestの累積タイミング（単一真実源）とズレることがある。
    # sentence_indicesを使って各シーンのタイミングをaudio基準で再計算する。
    if seg_timing:
        # セグメント別に最初のシーンを特定（共有セグメント対応）
        seg_first_scene = {}  # segment_index → first scene's original start
        for scene in scenes:
            si = scene.get("sentence_indices", [])
            if si and si[0] not in seg_first_scene:
                seg_first_scene[si[0]] = scene["start"]

        timing_corrected = 0
        for scene in scenes:
            si = scene.get("sentence_indices", [])
            if not si:
                continue
            first_idx = si[0]
            last_idx = si[-1]
            if first_idx >= len(seg_timing):
                continue

            # このシーンがセグメントを他のシーンと共有しているか判定
            sharing = [s for s in scenes if s.get("sentence_indices") == si and s["id"] != scene["id"]]

            if not sharing:
                # 単独所有: audioタイミングを直接使用
                new_start = seg_timing[first_idx][0]
                new_end = seg_timing[min(last_idx, len(seg_timing) - 1)][1]
            else:
                # 共有セグメント: オフセット補正で相対位置を維持
                orig_seg_start = seg_first_scene.get(first_idx, scene["start"])
                audio_seg_start = seg_timing[first_idx][0]
                offset = audio_seg_start - orig_seg_start
                new_start = scene["start"] + offset
                new_end = scene["end"] + offset

            old_start, old_end = scene["start"], scene["end"]
            scene["start"] = round(max(0, new_start), 3)
            scene["end"] = round(new_end, 3)
            if abs(old_start - scene["start"]) > 0.05 or abs(old_end - scene["end"]) > 0.05:
                timing_corrected += 1

        if timing_corrected:
            print(f"  Timing corrected: {timing_corrected} scenes aligned to audio manifest")

    # Build theme title from meta
    # theme_titleはscenes.jsonのmeta.theme_titleを優先（色タグ付き）
    # 未設定の場合はtopicをそのまま使用（お頭が手動で色タグを追加すること）
    topic = meta.get("topic", "")
    theme_title = meta.get("theme_title", topic)

    # Detect concentration_lines scenes from reviews
    concentration_scenes = []

    # Build timeline
    timeline = []
    kb_auto_index = 0

    for scene in scenes:
        sid = scene["id"]
        review = reviews.get(sid, {})
        review_fx = review.get("effects", {})
        review_kb = review.get("ken_burns", {})

        start = scene["start"]
        end = scene["end"]

        # --- info_panel layer ---
        params = {"asset": scene["asset"]}

        # Ken Burns settings（パネル素材は静止表示、それ以外はKen Burns有効）
        is_panel = '/panels/' in scene["asset"]
        kb = review_kb if review_kb else {}
        params["ken_burns"] = False if is_panel else kb.get("ken_burns", True)
        params["kb_intensity"] = kb.get("kb_intensity", 3.0)

        if kb.get("kb_direction"):
            params["kb_direction"] = kb["kb_direction"]
        if kb.get("kb_focus"):
            params["kb_focus"] = kb["kb_focus"]

        # Visual effects
        effects = {}
        if review_fx:
            if review_fx.get("flash"):
                effects["flash"] = True
            if review_fx.get("shake"):
                effects["shake"] = True
                effects["shake_intensity"] = review_fx.get("shake_intensity", 6)
            if review_fx.get("bounce_in"):
                effects["bounce_in"] = True
            if review_fx.get("rgb_shift"):
                effects["rgb_shift"] = True
                effects["rgb_intensity"] = review_fx.get("rgb_intensity", 3)
            if review_fx.get("concentration_lines"):
                concentration_scenes.append(sid)
                effects["concentration_lines"] = True

        # scenes.jsonのfxフィールドからも集中線を検出
        if scene.get("fx") == "concentration_lines" and sid not in concentration_scenes:
            concentration_scenes.append(sid)
            effects["concentration_lines"] = True

        if effects:
            params["effects"] = effects

        timeline.append({
            "layer": "info_panel",
            "time_start": start,
            "time_end": end,
            "params": params
        })

        # SE from review
        se_type = review.get("se")
        if se_type and se_type != "none" and se_type in SE_MAP:
            timeline.append({
                "layer": "se",
                "time_start": start,
                "time_end": end,
                "params": {
                    "action": "play_se",
                    "file": SE_MAP[se_type],
                    "type": se_type
                }
            })

        kb_auto_index += 1

    # --- subtitle layer ---
    # Use sentence_timings from audio_manifest for precise subtitle timing
    if sentence_timings:
        for st in sentence_timings:
            text = st["text"]
            offset = st["offset"]
            duration = st["duration"]

            # Split long subtitles
            parts = split_subtitle(text)
            if len(parts) == 1:
                # split_subtitleは末尾句読点を除去するため、除去後テキストを使う
                sub_params = {"text": parts[0]}
                # Check if this subtitle falls within a scene with shake
                for ev in timeline:
                    if ev["layer"] == "info_panel" and ev["time_start"] <= offset < ev["time_end"]:
                        scene_fx = ev["params"].get("effects", {})
                        if scene_fx.get("shake"):
                            sub_params["effects"] = {
                                "shake": True,
                                "shake_intensity": scene_fx.get("shake_intensity", 4)
                            }
                        break
                timeline.append({
                    "layer": "subtitle",
                    "time_start": offset,
                    "time_end": offset + duration,
                    "params": sub_params
                })
            else:
                # Split proportionally by character count
                total_chars = sum(len(p) for p in parts)
                t = offset
                for p in parts:
                    part_dur = duration * len(p) / total_chars
                    timeline.append({
                        "layer": "subtitle",
                        "time_start": round(t, 6),
                        "time_end": round(t + part_dur, 6),
                        "params": {"text": p}
                    })
                    t += part_dur  # ギャップなし（連続表示）
    else:
        # Fallback: use scene text directly
        for scene in scenes:
            parts = split_subtitle(scene["text"])
            dur = scene["end"] - scene["start"]
            total_chars = sum(len(p) for p in parts)
            t = scene["start"]
            for p in parts:
                part_dur = dur * len(p) / total_chars
                timeline.append({
                    "layer": "subtitle",
                    "time_start": round(t, 6),
                    "time_end": round(t + part_dur, 6),
                    "params": {"text": p}
                })
                t += part_dur

    # --- info_panel ギャップ自動修正 ---
    # 各info_panelのtime_endを次のinfo_panelのtime_startまで延長して黒フレームを防ぐ
    info_panels_in_timeline = [e for e in timeline if e["layer"] == "info_panel"]
    info_panels_in_timeline.sort(key=lambda e: e["time_start"])
    gaps_fixed = 0
    for i in range(len(info_panels_in_timeline) - 1):
        curr = info_panels_in_timeline[i]
        next_panel = info_panels_in_timeline[i + 1]
        if curr["time_end"] < next_panel["time_start"]:
            curr["time_end"] = next_panel["time_start"]
            gaps_fixed += 1
    # 最後のinfo_panelをtotal_durationまで延長
    if info_panels_in_timeline:
        last_panel = info_panels_in_timeline[-1]
        if last_panel["time_end"] < total_duration:
            last_panel["time_end"] = total_duration
            gaps_fixed += 1
    if gaps_fixed:
        print(f"  Info panel gaps fixed: {gaps_fixed}")

    # Sort timeline by time_start, then layer priority
    layer_order = {"info_panel": 0, "se": 1, "subtitle": 2, "bottom_text": 3}
    timeline.sort(key=lambda e: (e["time_start"], layer_order.get(e["layer"], 9)))

    # BGM selection from meta.mood or default
    bgm_mood = meta.get("mood", "dramatic")  # default: dramatic
    bgm_file = BGM_MAP.get(bgm_mood, BGM_MAP["dramatic"])
    bgm_volume = BGM_VOLUME_MAP.get(bgm_mood, BGM_VOLUME_DEFAULT)

    # Build render plan
    render_plan = {
        "canvas": {"width": 1080, "height": 1920, "fps": 30},
        "duration_sec": round(total_duration, 2),
        "layout": {
            "type": "combined",
            "top_bar": {"height": 656, "font_size": 72},
            "content": {"y": 656, "width": 1080, "height": 608},
            "subtitle": {"y": 1294, "font_size": 84, "outline_width": 10, "height": 360},
            "effects": {}
        },
        "bgm": {
            "file": bgm_file,
            "volume": bgm_volume,
            "loop": True
        },
        "theme_title": theme_title,
        "concentration_scenes": concentration_scenes,
        "timeline": timeline
    }

    # Save
    output_path = theme_path / "render_plan.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(render_plan, f, ensure_ascii=False, indent=2)

    # Summary
    info_panels = sum(1 for e in timeline if e["layer"] == "info_panel")
    subtitles = sum(1 for e in timeline if e["layer"] == "subtitle")
    se_count = sum(1 for e in timeline if e["layer"] == "se")
    fx_count = sum(1 for e in timeline if e["layer"] == "info_panel" and e["params"].get("effects"))
    print(f"render_plan.json generated:")
    print(f"  Duration: {total_duration:.1f}s")
    print(f"  Info panels: {info_panels}")
    print(f"  Subtitles: {subtitles}")
    print(f"  SE events: {se_count}")
    print(f"  Scenes with FX: {fx_count}")
    print(f"  Concentration scenes: {len(concentration_scenes)}")
    print(f"  Output: {output_path}")

    # === Preflight Errors (生成を停止) ===
    errors = []

    # チェック0: Tinderレビュー完了確認（モードA必須、モードBは--skip-reviewで回避）
    if skip_review:
        print("  ⏭️  Tinderレビューチェックをスキップ（--skip-review）")
    elif not review_path.exists():
        errors.append(
            f"  scene_review.json が見つかりません\n"
            f"    → Phase 3 Tinderレビューを実施してください\n"
            f"    → モードBの場合: --skip-review フラグで回避可能"
        )
    elif review_path.exists():
        unapproved = []
        for scene in scenes:
            sid = scene["id"]
            review_entry = reviews.get(sid, {})
            # panel_mapping_reviewer.py は "status": "ok"/"ng" を書き込む
            is_approved = (review_entry.get("status") == "ok" or
                          review_entry.get("approved", False))
            if not is_approved:
                unapproved.append(sid)
        if unapproved:
            errors.append(
                f"  未承認シーンがあります: {', '.join(unapproved)}\n"
                f"    → Phase 3 Tinderレビューで全シーンを承認してください\n"
                f"    → python3 scripts/panel_mapping_reviewer.py --shorts {theme_dir}"
            )

    # チェック: Geminiシーンにref_imageが設定されているか（正方形画像防止）
    missing_ref = []
    for s in scenes:
        if s.get("asset_type", "gemini") == "gemini" and not s.get("ref_image"):
            missing_ref.append(s["id"])
    if missing_ref:
        errors.append(
            f"  ref_image未設定のGeminiシーン: {', '.join(missing_ref)}\n"
            f"    → ref_imageがないと正方形(1024x1024)で生成される\n"
            f"    → scenes.jsonで \"ref_image\": \"ref\" を追加してください"
        )

    # チェック: asset_type=\"i2v\"は無効（assetパスを.mp4に変更するのが正しいフロー）
    i2v_scenes = [s["id"] for s in scenes if s.get("asset_type") == "i2v"]
    if i2v_scenes:
        errors.append(
            f"  asset_type=\"i2v\"のシーン: {', '.join(i2v_scenes)}\n"
            f"    → asset_typeは\"gemini\"のまま、assetパスを.mp4に変更してください\n"
            f"    → 正しいi2vフロー: PNG生成→外部でmp4生成→assetパス書き換え"
        )

    # チェック: assetパスが.mp4だがファイルが存在しない
    missing_mp4 = []
    for s in scenes:
        asset = s.get("asset", "")
        if asset.endswith(".mp4"):
            full_path = PROJECT_ROOT / asset
            if not full_path.exists():
                missing_mp4.append(f"{s['id']} ({asset})")
    if missing_mp4:
        errors.append(
            f"  存在しないmp4ファイル: {', '.join(missing_mp4)}\n"
            f"    → i2v動画を生成してassets/scenes/に配置してください\n"
            f"    → mp4配置前にrender_planを生成しないでください"
        )

    # チェック: mp4シーンが冒頭から連続しているか（i2vルール）
    mp4_scene_ids = [s["id"] for s in scenes if s.get("asset", "").endswith(".mp4")]
    if mp4_scene_ids:
        for i, expected_id in enumerate(mp4_scene_ids):
            actual_id = scenes[i]["id"] if i < len(scenes) else None
            if actual_id != expected_id:
                errors.append(
                    f"  mp4シーンが冒頭から連続していません: {mp4_scene_ids}\n"
                    f"    → i2v動画は冒頭の連続シーン（scene_01, scene_02, ...）に限定\n"
                    f"    → 途中のシーンにmp4を割り当てないでください"
                )
                break

    # === Preflight Warnings ===
    warnings = []

    # チェック1: theme_titleに色タグが含まれているか
    if "{red:" not in theme_title and "{red_big:" not in theme_title:
        warnings.append(
            f"  theme_titleに色タグがありません: \"{theme_title}\"\n"
            f"    → 核心ワードを {{red:キーワード}} で囲んでください\n"
            f"    → scenes.jsonのmeta.theme_titleに設定"
        )

    # チェック2: 全シーンがGeminiのみ（素材タイプ混在チェック）
    asset_types = set()
    for s in scenes:
        at = s.get("asset_type", "gemini")
        asset_types.add(at)
    if asset_types == {"gemini"} and len(scenes) >= 10:
        warnings.append(
            f"  全{len(scenes)}シーンがGemini画像のみです\n"
            f"    → 数値データがあればPillow(asset_type:pillow)を検討\n"
            f"    → 風景・抽象シーンがあればPixabay(asset_type:pixabay)を検討"
        )

    # チェック3: scene_01（オープニング）のflash/shake禁止 + time_start=0.0
    first_panel = None
    for ev in timeline:
        if ev["layer"] == "info_panel":
            first_panel = ev
            break
    if first_panel:
        fp_effects = first_panel.get("params", {}).get("effects", {})
        if fp_effects.get("flash"):
            warnings.append(
                f"  scene_01にflash効果あり → 開始直後の白フラッシュの原因\n"
                f"    → scene_review.jsonからflashを削除してください"
            )
        if fp_effects.get("shake"):
            warnings.append(
                f"  scene_01にshake効果あり → 開始直後の映像揺れの原因\n"
                f"    → scene_review.jsonからshakeを削除してください"
            )
        if first_panel.get("time_start", 0) > 0:
            warnings.append(
                f"  scene_01のtime_startが{first_panel['time_start']}s → 冒頭ブラックアウトの原因\n"
                f"    → time_start=0.0に修正してください"
            )

    # チェック4: shake効果が3箇所を超えていないか
    shake_count = sum(
        1 for ev in timeline
        if ev["layer"] == "info_panel" and ev.get("params", {}).get("effects", {}).get("shake")
    )
    if shake_count > 3:
        warnings.append(
            f"  shake効果が{shake_count}箇所 → 2〜3箇所に厳選推奨\n"
            f"    → 最もインパクトのある瞬間のみに絞ってください"
        )

    # チェック5: 画像10枚未満ゲート
    if info_panels < 10:
        warnings.append(
            f"  画像が{info_panels}枚 → 10枚未満はシーン不足\n"
            f"    → シーン分割を見直して追加してください"
        )

    if errors:
        print(f"\n❌ Preflight Errors ({len(errors)}) — render_plan生成を中止:")
        for e in errors:
            print(e)
        return False

    if warnings:
        print(f"\n⚠️  Preflight Warnings ({len(warnings)}):")
        for w in warnings:
            print(w)

    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/generate_render_plan.py <テーマフォルダ>")
        print("Example: python3 scripts/generate_render_plan.py エイミー先生の時事ニュース/中革連ブーメラン")
        sys.exit(1)

    theme_dir = sys.argv[1]
    skip_review = "--skip-review" in sys.argv
    if not generate_render_plan(theme_dir, skip_review=skip_review):
        sys.exit(1)


if __name__ == "__main__":
    main()
