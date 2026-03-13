#!/usr/bin/env python3
"""
パネルマッピングレビューアプリ v4 - Tinder方式（横動画+Shorts両対応）

スワイプ左=NG、スワイプ右=OK。
NG時は修正方法を選択。
結果はpanel_review.jsonに即時保存。

使い方:
    # 横動画（従来通り）
    python3 scripts/panel_mapping_reviewer.py [audio_manifest.json]

    # Shorts（9:16縦動画）
    python3 scripts/panel_mapping_reviewer.py --shorts <scenes.json>
"""

import http.server
import json
import os
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
REVIEW_FILE = PROJECT_ROOT / "assets" / "panel_review.json"

# Mode: "horizontal" or "shorts" — set in main()
REVIEWER_MODE = "horizontal"

server_state = {
    "panels": [],
    "done": False,
}


def load_review():
    if REVIEW_FILE.exists():
        with open(REVIEW_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_review(review_data):
    REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_FILE, "w", encoding="utf-8") as f:
        json.dump(review_data, f, ensure_ascii=False, indent=2)


def load_data(manifest_path=None):
    image_map_path = PROJECT_ROOT / "image_map.json"
    with open(image_map_path, "r", encoding="utf-8") as f:
        image_map = json.load(f)

    # Auto-fix asset paths: add "assets/" prefix if missing
    for panel in image_map.get("panels", []):
        asset = panel.get("asset", "")
        if asset and not asset.startswith("assets/"):
            panel["asset"] = f"assets/{asset}"

    script_texts = {}
    if manifest_path and Path(manifest_path).exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        for seg in manifest.get("segments", []):
            idx = seg.get("index", seg.get("section_index", 0))
            text = seg.get("text", "")
            speaker = seg.get("speaker_display", seg.get("speaker", ""))
            if idx not in script_texts:
                script_texts[idx] = []
            script_texts[idx].append({"speaker": speaker, "text": text})

    panels = []
    for panel in image_map.get("panels", []):
        seg_start, seg_end = panel["segment_range"]
        lines = []
        for i in range(seg_start, seg_end + 1):
            if i in script_texts:
                for entry in script_texts[i]:
                    lines.append(entry)

        asset_path = panel.get("asset", "")
        full_path = PROJECT_ROOT / asset_path
        exists = full_path.exists() if asset_path else False

        panels.append({
            "id": panel["id"],
            "segment_range": panel["segment_range"],
            "description": panel.get("description", ""),
            "asset": asset_path,
            "asset_exists": exists,
            "source": panel.get("source", ""),
            "script_lines": lines,
        })

    return panels


def load_shorts_data(scenes_json_path):
    """Shorts用: scenes.jsonからシーンデータを読み込む"""
    scenes_path = Path(scenes_json_path)
    with open(scenes_path, "r", encoding="utf-8") as f:
        scenes_data = json.load(f)

    base_dir = scenes_path.parent
    panels = []
    for i, scene in enumerate(scenes_data.get("scenes", [])):
        asset_path = scene.get("asset", "")
        # asset pathをPROJECT_ROOTからの相対パスに変換
        # 優先順位: PROJECT_ROOT相対 > base_dir相対 > 絶対パス
        if asset_path:
            if Path(asset_path).is_absolute():
                full_path = Path(asset_path)
            elif (PROJECT_ROOT / asset_path).exists():
                full_path = PROJECT_ROOT / asset_path
            elif (base_dir / asset_path).exists():
                full_path = base_dir / asset_path
            else:
                # どちらにも存在しない場合、PROJECT_ROOT相対をデフォルトとする
                full_path = PROJECT_ROOT / asset_path
            exists = full_path.exists()
            # サーバーからのアクセス用にPROJECT_ROOT相対パスに変換
            try:
                rel_path = full_path.relative_to(PROJECT_ROOT)
                asset_path = str(rel_path)
            except ValueError:
                asset_path = str(full_path)
        else:
            exists = False

        # Auto-suggest FX based on scene content
        suggested_fx = suggest_fx_for_scene(scene, i, len(scenes_data.get("scenes", [])))

        panels.append({
            "id": scene["id"],
            "segment_range": [scene.get("sentence_indices", [0])[0],
                              scene.get("sentence_indices", [-1])[-1]]
                              if scene.get("sentence_indices") else [0, 0],
            "description": scene.get("description", ""),
            "asset": asset_path,
            "asset_exists": exists,
            "source": "gemini",
            "script_lines": [{"speaker": "エイミー先生", "text": scene.get("text", "")}],
            "timing": f"{scene.get('start', 0):.1f}s - {scene.get('end', 0):.1f}s ({scene.get('end', 0) - scene.get('start', 0):.1f}s)",
            "prompt": scene.get("prompt", ""),
            "suggested_fx": suggested_fx,
        })

    return panels


def suggest_fx_for_scene(scene, index, total_scenes):
    """シーンの内容からFX/KB/SEを自動提案する"""
    desc = (scene.get("description", "") + " " + scene.get("text", "")).lower()
    ref = scene.get("ref_image")
    is_first = index == 0
    is_last = index == total_scenes - 1

    effects = {}
    kb = {"ken_burns": True, "kb_intensity": 3.0}
    se = None

    # --- KB Direction ロジック ---
    # エイミー先生のシーン → zoom_in_center（キャラにフォーカス）
    if ref == "amy":
        kb["kb_direction"] = "zoom_in_center"
        kb["kb_intensity"] = 2.5
    # 政治家のシーン → ゆっくりzoom in
    elif ref == "politician":
        kb["kb_direction"] = "zoom_in"
        kb["kb_intensity"] = 2.0
    # データ・テーブル系 → pan（横移動で情報を見せる）
    elif any(k in desc for k in ["データ", "万円", "税金", "料亭", "テーブル"]):
        kb["kb_direction"] = "pan_right"
        kb["kb_intensity"] = 2.0
    # 対比・分割シーン → zoom_out（全体を見せる）
    elif any(k in desc for k in ["対比", "分割", "split", "落選", "手のひら"]):
        kb["kb_direction"] = "zoom_out"
        kb["kb_intensity"] = 2.5

    # --- Visual FX ロジック ---
    # 怒り・ツッコミ・崩壊系 → flash + shake
    if any(k in desc for k in ["怒り", "怒る", "ツッコミ", "叩き", "痛烈", "カウンター",
                                 "衝撃", "大騒ぎ", "抗議",
                                 "崩壊", "暴落", "破綻", "焼け野原", "崩れ"]):
        effects["flash"] = True
        effects["shake"] = True
        effects["shake_intensity"] = 5
        kb["kb_intensity"] = 3.0
    # インパクト・ブーメラン → flash + shake + rgb_shift
    elif any(k in desc for k in ["ブーメラン", "インパクト", "正真正銘", "本性"]):
        effects["flash"] = True
        effects["shake"] = True
        effects["shake_intensity"] = 8
        effects["rgb_shift"] = True
        kb["kb_intensity"] = 3.5
    # 驚き・危機系 → flash のみ
    elif any(k in desc for k in ["にやけ", "ポロリ", "信じられ", "とんでもない",
                                   "危機", "脱出", "逃げ", "売り切"]):
        effects["flash"] = True
    # 最初と最後 → bounce_in（登場感）
    if is_first or is_last:
        effects["bounce_in"] = True

    # --- SE ロジック ---
    if any(k in desc for k in ["ブーメラン", "インパクト", "正真正銘",
                                 "崩壊", "暴落", "破綻", "焼け野原"]):
        se = "impact"
    elif any(k in desc for k in ["怒り", "ツッコミ", "痛烈", "カウンター",
                                   "しかし", "ところが", "一方", "転換"]):
        se = "whoosh"
    elif any(k in desc for k in ["信じられ", "とんでもない", "万円",
                                   "驚", "衝撃", "脱出", "逃げ", "売り切"]):
        se = "surprise"

    return {
        "effects": effects if effects else None,
        "ken_burns": kb,
        "se": se,
    }


def build_html():
    return """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>パネルレビュー - Tinder方式</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
    background: #0f0f1a;
    color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, 'Hiragino Sans', sans-serif;
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.topbar {
    background: #16213e;
    padding: 10px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #2a2a4e;
    flex-shrink: 0;
    z-index: 10;
}
.topbar h1 { font-size: 18px; color: #fff; }
.progress-info { display: flex; gap: 16px; align-items: center; font-size: 13px; }
.cnt-ok { color: #4CAF50; font-weight: 700; }
.cnt-ng { color: #f44336; font-weight: 700; }
.cnt-rem { color: #888; }
.progress-bar-wrap { width: 160px; height: 6px; background: #2a2a4e; border-radius: 3px; overflow: hidden; }
.progress-bar { height: 100%; background: #4CAF50; transition: width 0.3s; }

.card-area {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    position: relative;
    overflow: hidden;
}

.card {
    width: 720px;
    max-width: 90vw;
    max-height: calc(100vh - 160px);
    background: #1a1a2e;
    border-radius: 20px;
    overflow: hidden;
    box-shadow: 0 10px 40px rgba(0,0,0,0.5);
    position: relative;
    transition: transform 0.3s ease, opacity 0.3s ease;
    cursor: grab;
    display: flex;
    flex-direction: column;
}
.card.swiping { transition: none; cursor: grabbing; }
.card.swipe-right { transform: translateX(150%) rotate(20deg); opacity: 0; }
.card.swipe-left { transform: translateX(-150%) rotate(-20deg); opacity: 0; }

.card-badge {
    position: absolute;
    top: 20px;
    padding: 8px 24px;
    border-radius: 8px;
    font-size: 28px;
    font-weight: 900;
    z-index: 5;
    opacity: 0;
    transition: opacity 0.2s;
    border: 4px solid;
    transform: rotate(-15deg);
}
.badge-ok { right: 20px; color: #4CAF50; border-color: #4CAF50; background: rgba(76,175,80,0.15); }
.badge-ng { left: 20px; color: #f44336; border-color: #f44336; background: rgba(244,67,54,0.15); transform: rotate(15deg); }

.card-media {
    height: 360px;
    background: #0a0a1a;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    flex-shrink: 0;
    overflow: hidden;
}
/* Shorts mode overrides (applied via JS) */
body.shorts-mode .card { width: 420px; }
body.shorts-mode .card-media { height: 520px; }
body.shorts-mode .card-info { max-height: 160px; }
.timing-tag {
    display: inline-block;
    background: #1A73E8;
    color: #fff;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    margin-left: 8px;
}
.card-media img { max-width: 100%; max-height: 100%; object-fit: contain; }
.card-media video { max-width: 100%; max-height: 100%; object-fit: contain; }
.card-media .missing { color: #f44336; font-size: 18px; text-align: center; }
.source-tag {
    position: absolute;
    top: 8px;
    left: 8px;
    padding: 3px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    color: #fff;
}
.src-pillow { background: #1A73E8; }
.src-pixabay_video { background: #E8710A; }
.src-wikimedia { background: #188038; }

.card-info {
    padding: 16px 20px;
    flex: 1;
    overflow-y: auto;
    min-height: 0;
}
.card-title {
    font-size: 16px;
    font-weight: 800;
    color: #fff;
    margin-bottom: 4px;
}
.card-meta {
    font-size: 12px;
    color: #888;
    margin-bottom: 8px;
}
.card-desc {
    font-size: 13px;
    color: #4CAF50;
    margin-bottom: 10px;
    font-weight: 600;
}
.script-line {
    margin-bottom: 4px;
    font-size: 12px;
    line-height: 1.4;
}
.spk { display: inline-block; padding: 1px 5px; border-radius: 3px; font-size: 9px; font-weight: 700; margin-right: 3px; }
.spk-a { background: #9334E6; color: #fff; }
.spk-s { background: #E8710A; color: #fff; }

.card-info::-webkit-scrollbar { width: 4px; }
.card-info::-webkit-scrollbar-track { background: transparent; }
.card-info::-webkit-scrollbar-thumb { background: #444; border-radius: 2px; }

.actions {
    background: #16213e;
    border-top: 2px solid #2a2a4e;
    padding: 12px 20px;
    display: flex;
    justify-content: center;
    gap: 24px;
    align-items: center;
    flex-shrink: 0;
}
.act-btn {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    border: 3px solid;
    background: transparent;
    cursor: pointer;
    font-size: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s;
}
.btn-ng-act { border-color: #f44336; color: #f44336; }
.btn-ng-act:hover { background: #f44336; color: #fff; }
.btn-undo { border-color: #E8710A; color: #E8710A; width: 48px; height: 48px; font-size: 20px; }
.btn-undo:hover { background: #E8710A; color: #fff; }
.btn-ok-act { border-color: #4CAF50; color: #4CAF50; }
.btn-ok-act:hover { background: #4CAF50; color: #fff; }

.nav-dots {
    display: flex;
    gap: 3px;
    justify-content: center;
    padding: 6px 0;
    flex-wrap: wrap;
    max-width: 400px;
}
.dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #2a2a4e;
    cursor: pointer;
    transition: all 0.2s;
}
.dot.current { background: #1A73E8; transform: scale(1.4); }
.dot.ok { background: #4CAF50; }
.dot.ng { background: #f44336; }

/* NG Modal */
.modal-overlay {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.7);
    z-index: 100;
    align-items: center;
    justify-content: center;
}
.modal-overlay.active { display: flex; }
.modal {
    background: #1a1a2e;
    border-radius: 16px;
    padding: 24px;
    width: 480px;
    max-width: 90vw;
    border: 2px solid #2a2a4e;
}
.modal h3 { color: #f44336; font-size: 18px; margin-bottom: 16px; }
.modal textarea {
    width: 100%;
    background: #0a0a1a;
    border: 1px solid #333;
    border-radius: 8px;
    color: #fff;
    padding: 10px;
    font-size: 13px;
    min-height: 60px;
    resize: vertical;
    font-family: inherit;
    margin-bottom: 12px;
}
.modal-label { font-size: 13px; color: #888; margin-bottom: 8px; }
.fix-options { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.fix-opt {
    padding: 10px 16px;
    border-radius: 8px;
    border: 2px solid #2a2a4e;
    background: transparent;
    color: #e0e0e0;
    font-size: 14px;
    cursor: pointer;
    text-align: left;
    transition: all 0.2s;
}
.fix-opt:hover { border-color: #f44336; background: rgba(244,67,54,0.1); }
.fix-opt.selected { border-color: #f44336; background: rgba(244,67,54,0.2); color: #fff; }
.modal-actions { display: flex; gap: 8px; }
.modal-actions button {
    flex: 1;
    padding: 10px;
    border-radius: 8px;
    border: none;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
}
.btn-cancel { background: #5F6368; color: #fff; }
.btn-submit-ng { background: #f44336; color: #fff; }
.btn-submit-ng:disabled { opacity: 0.4; cursor: not-allowed; }

/* FX Sidebar (Shorts mode) */
.fx-sidebar {
    display: none;
    width: 320px;
    background: #16213e;
    border-left: 2px solid #2a2a4e;
    padding: 12px;
    overflow-y: auto;
    flex-shrink: 0;
}
.shorts-mode .fx-sidebar { display: flex; flex-direction: column; }
.shorts-mode #app { flex-direction: row; flex-wrap: wrap; }
.shorts-mode .topbar { width: 100%; }
.shorts-mode .main-content { display: flex; flex: 1; overflow: hidden; }
.shorts-mode .card-area { flex: 1; }

.fx-section { margin-bottom: 10px; }
.fx-section h4 { color: #1A73E8; font-size: 13px; margin-bottom: 6px; border-bottom: 1px solid #2a2a4e; padding-bottom: 3px; }
.fx-toggles { display: flex; flex-wrap: wrap; gap: 4px; }
.fx-toggle {
    padding: 4px 10px;
    border-radius: 16px;
    border: 2px solid #2a2a4e;
    background: transparent;
    color: #aaa;
    font-size: 11px;
    cursor: pointer;
    transition: all 0.2s;
}
.fx-toggle:hover { border-color: #1A73E8; color: #fff; }
.fx-toggle.active { border-color: #1A73E8; background: rgba(26,115,232,0.25); color: #fff; font-weight: 700; }
.kb-select, .se-select {
    width: 100%;
    background: #0a0a1a;
    border: 1px solid #333;
    border-radius: 6px;
    color: #fff;
    padding: 6px 8px;
    font-size: 12px;
    font-family: inherit;
}
.kb-row { display: flex; gap: 6px; margin-bottom: 4px; align-items: center; }
.kb-row label { font-size: 11px; color: #888; min-width: 70px; }
.kb-row input[type=range] { flex: 1; }
.kb-row .val { font-size: 11px; color: #1A73E8; min-width: 28px; text-align: right; }
.fx-presets { display: flex; gap: 4px; margin-bottom: 8px; flex-wrap: wrap; }
.fx-preset {
    padding: 3px 8px;
    border-radius: 10px;
    border: 1px solid #444;
    background: transparent;
    color: #888;
    font-size: 10px;
    cursor: pointer;
}
.fx-preset:hover { border-color: #E8710A; color: #fff; }
.fx-preset.active-preset { border-color: #E8710A; background: rgba(232,113,10,0.2); color: #fff; }

/* Preview button */
.fx-preview-btn {
    padding: 2px 6px;
    border-radius: 8px;
    border: 1px solid #555;
    background: transparent;
    color: #888;
    font-size: 9px;
    cursor: pointer;
    margin-left: 4px;
    transition: all 0.2s;
}
.fx-preview-btn:hover { border-color: #E8710A; color: #E8710A; }

/* FX Preview Overlay */
.fx-preview-overlay {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    pointer-events: none;
    z-index: 10;
}

/* Flash animation */
@keyframes fx-flash {
    0% { opacity: 0; }
    15% { opacity: 0.9; }
    100% { opacity: 0; }
}
.preview-flash {
    background: white;
    animation: fx-flash 0.5s ease-out;
}

/* Shake animation */
@keyframes fx-shake {
    0%, 100% { transform: translate(0,0) rotate(0deg); }
    10% { transform: translate(-6px, 2px) rotate(-1deg); }
    20% { transform: translate(5px, -3px) rotate(1deg); }
    30% { transform: translate(-4px, 1px) rotate(-0.5deg); }
    40% { transform: translate(3px, -2px) rotate(0.5deg); }
    50% { transform: translate(-2px, 3px) rotate(-0.3deg); }
    60% { transform: translate(4px, -1px) rotate(0.3deg); }
    70% { transform: translate(-3px, 2px) rotate(-0.2deg); }
    80% { transform: translate(2px, -1px) rotate(0.2deg); }
    90% { transform: translate(-1px, 1px) rotate(0deg); }
}
.preview-shake .card-media img,
.preview-shake .card-media video {
    animation: fx-shake 0.6s ease-out;
}

/* Bounce animation */
@keyframes fx-bounce {
    0% { transform: scale(0.3); opacity: 0; }
    40% { transform: scale(1.08); opacity: 1; }
    60% { transform: scale(0.95); }
    80% { transform: scale(1.02); }
    100% { transform: scale(1.0); }
}
.preview-bounce .card-media img,
.preview-bounce .card-media video {
    animation: fx-bounce 0.7s ease-out;
}

/* RGB Shift animation */
@keyframes fx-rgb {
    0% { filter: none; }
    20% { filter: hue-rotate(90deg) saturate(2) brightness(1.1); }
    40% { filter: hue-rotate(180deg) saturate(1.5); }
    60% { filter: hue-rotate(270deg) saturate(2) brightness(1.1); }
    80% { filter: hue-rotate(360deg) saturate(1.5); }
    100% { filter: none; }
}
.preview-rgb .card-media img,
.preview-rgb .card-media video {
    animation: fx-rgb 0.8s ease-out;
}

/* Concentration Lines overlay */
@keyframes fx-conc {
    0% { opacity: 0; }
    30% { opacity: 0.7; }
    100% { opacity: 0; }
}
.preview-conc-overlay {
    background: radial-gradient(ellipse at center, transparent 30%, rgba(0,0,0,0.6) 70%);
    animation: fx-conc 1.0s ease-out;
}

/* Ken Burns Preview animations */
@keyframes kb-zoom-in {
    0% { transform: scale(1.0); }
    100% { transform: scale(1.15); }
}
@keyframes kb-zoom-out {
    0% { transform: scale(1.15); }
    100% { transform: scale(1.0); }
}
@keyframes kb-zoom-in-center {
    0% { transform: scale(1.0) translate(0, 0); }
    100% { transform: scale(1.12) translate(0, -2%); }
}
@keyframes kb-pan-left {
    0% { transform: translateX(0) scale(1.05); }
    100% { transform: translateX(-5%) scale(1.05); }
}
@keyframes kb-pan-right {
    0% { transform: translateX(0) scale(1.05); }
    100% { transform: translateX(5%) scale(1.05); }
}
.preview-kb .card-media { overflow: hidden; }
.preview-kb-zoom_in .card-media img,
.preview-kb-zoom_in .card-media video { animation: kb-zoom-in 1.5s ease-in-out forwards; }
.preview-kb-zoom_out .card-media img,
.preview-kb-zoom_out .card-media video { animation: kb-zoom-out 1.5s ease-in-out forwards; }
.preview-kb-zoom_in_center .card-media img,
.preview-kb-zoom_in_center .card-media video { animation: kb-zoom-in-center 1.5s ease-in-out forwards; }
.preview-kb-pan_left .card-media img,
.preview-kb-pan_left .card-media video { animation: kb-pan-left 1.5s ease-in-out forwards; }
.preview-kb-pan_right .card-media img,
.preview-kb-pan_right .card-media video { animation: kb-pan-right 1.5s ease-in-out forwards; }

/* Done screen */
.done { display: none; flex-direction: column; align-items: center; justify-content: center; height: 100vh; }
.done h2 { font-size: 36px; color: #4CAF50; margin-bottom: 16px; }
.done p { color: #888; font-size: 16px; margin-bottom: 6px; }

/* Drop zone */
.drop-zone {
    border: 2px dashed #4CAF50;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 12px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s;
    background: rgba(76,175,80,0.05);
}
.drop-zone.dragover { background: rgba(76,175,80,0.15); border-color: #81C784; }
.drop-zone .drop-icon { font-size: 32px; margin-bottom: 4px; }
.drop-zone p { color: #aaa; font-size: 13px; }
.drop-zone img { max-width: 200px; max-height: 120px; border-radius: 8px; margin-top: 8px; }
.drop-zone .uploaded-name { color: #4CAF50; font-size: 12px; margin-top: 4px; }

/* Keyboard hints */
.hints {
    position: absolute;
    bottom: 8px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 11px;
    color: #555;
}
</style>
</head>
<body>

<div id="app">
    <div class="topbar">
        <h1>Panel Review</h1>
        <div class="progress-info">
            <span>OK: <span class="cnt-ok" id="cOk">0</span></span>
            <span>NG: <span class="cnt-ng" id="cNg">0</span></span>
            <span class="cnt-rem" id="cRem">36 remaining</span>
            <div class="progress-bar-wrap"><div class="progress-bar" id="pBar"></div></div>
        </div>
    </div>

    <div class="main-content">
        <div style="display:flex;flex-direction:column;flex:1;overflow:hidden;">
            <div class="card-area" id="cardArea">
                <div class="card" id="card">
                    <div class="card-badge badge-ok" id="badgeOk">OK</div>
                    <div class="card-badge badge-ng" id="badgeNg">NG</div>
                    <div class="card-media" id="media"></div>
                    <div class="card-info" id="info"></div>
                </div>
                <div class="hints">Arrow keys or swipe: Left=NG Right=OK | U=Undo</div>
            </div>

            <div class="actions">
                <button class="act-btn btn-ng-act" onclick="doNg()" title="NG (Left arrow)">X</button>
                <button class="act-btn btn-undo" onclick="doUndo()" title="Undo (U)">&#8617;</button>
                <div>
                    <div class="nav-dots" id="dots"></div>
                </div>
                <button class="act-btn btn-ok-act" onclick="doOk()" title="OK (Right arrow)">&#10003;</button>
            </div>
        </div>

        <div class="fx-sidebar" id="fxSidebar">
            <div class="fx-section">
                <h4>Presets</h4>
                <div class="fx-presets">
                    <button class="fx-preset" onclick="applyFxPreset('calm')">Calm</button>
                    <button class="fx-preset" onclick="applyFxPreset('dramatic')">Dramatic</button>
                    <button class="fx-preset" onclick="applyFxPreset('impact')">Impact</button>
                    <button class="fx-preset" onclick="applyFxPreset('none')">None</button>
                </div>
            </div>

            <div class="fx-section">
                <h4>Visual FX</h4>
                <div class="fx-toggles">
                    <button class="fx-toggle" data-fx="flash" onclick="toggleFx(this)">Flash</button><button class="fx-preview-btn" onclick="previewFx('flash')">&#9654;</button>
                    <button class="fx-toggle" data-fx="shake" onclick="toggleFx(this)">Shake</button><button class="fx-preview-btn" onclick="previewFx('shake')">&#9654;</button>
                    <button class="fx-toggle" data-fx="bounce_in" onclick="toggleFx(this)">Bounce</button><button class="fx-preview-btn" onclick="previewFx('bounce')">&#9654;</button>
                    <button class="fx-toggle" data-fx="rgb_shift" onclick="toggleFx(this)">RGB</button><button class="fx-preview-btn" onclick="previewFx('rgb')">&#9654;</button>
                    <button class="fx-toggle" data-fx="concentration_lines" onclick="toggleFx(this)">集中線</button><button class="fx-preview-btn" onclick="previewFx('conc')">&#9654;</button>
                </div>
                <div class="kb-row" style="margin-top:6px;">
                    <label>Shake強度</label>
                    <input type="range" id="fxShakeInt" min="2" max="12" value="6" oninput="document.getElementById('fxShakeVal').textContent=this.value">
                    <span class="val" id="fxShakeVal">6</span>
                </div>
            </div>

            <div class="fx-section">
                <h4>Ken Burns <button class="fx-preview-btn" onclick="previewKb()">&#9654; Preview</button></h4>
                <div class="kb-row">
                    <label>Direction</label>
                    <select class="kb-select" id="kbDirection">
                        <option value="auto">Auto</option>
                        <option value="zoom_in">Zoom In</option>
                        <option value="zoom_out">Zoom Out</option>
                        <option value="zoom_in_center">Zoom Center</option>
                        <option value="pan_left">Pan Left</option>
                        <option value="pan_right">Pan Right</option>
                    </select>
                </div>
                <div class="kb-row">
                    <label>Intensity</label>
                    <input type="range" id="kbIntensity" min="0.5" max="5.0" step="0.5" value="3.0" oninput="document.getElementById('kbIntVal').textContent=this.value">
                    <span class="val" id="kbIntVal">3.0</span>
                </div>
                <div class="kb-row">
                    <label>Focus X</label>
                    <input type="range" id="kbFocusX" min="0.0" max="1.0" step="0.05" value="0.5" oninput="document.getElementById('kbFxVal').textContent=this.value">
                    <span class="val" id="kbFxVal">0.5</span>
                </div>
                <div class="kb-row">
                    <label>Focus Y</label>
                    <input type="range" id="kbFocusY" min="0.0" max="1.0" step="0.05" value="0.4" oninput="document.getElementById('kbFyVal').textContent=this.value">
                    <span class="val" id="kbFyVal">0.4</span>
                </div>
            </div>

            <div class="fx-section">
                <h4>SE（効果音）</h4>
                <div style="display:flex;gap:6px;align-items:center;">
                    <select class="se-select" id="seSelect" style="flex:1;">
                        <option value="none">なし</option>
                        <option value="whoosh">Whoosh</option>
                        <option value="impact">Impact</option>
                        <option value="surprise">Surprise</option>
                        <option value="tension">Tension</option>
                    </select>
                    <button class="fx-preview-btn" onclick="previewSe()" style="padding:4px 10px;font-size:11px;">&#9654; Play</button>
                </div>
            </div>
        </div>
    </div>
</div>

<div class="modal-overlay" id="ngModal">
    <div class="modal">
        <h3>NG - 修正方法を選択</h3>
        <div class="modal-label">修正コメント:</div>
        <textarea id="ngComment" placeholder="何が問題か記入（例: 内容と合わない、縦長で見切れる等）"></textarea>
        <div class="modal-label">修正方法:</div>
        <div class="fix-options">
            <button class="fix-opt" data-fix="re_research" onclick="selectFix(this)">再リサーチ（別クエリで再検索）</button>
            <button class="fix-opt" data-fix="pillow" onclick="selectFix(this)">Pillow代替（テキストパネル生成）</button>
            <button class="fix-opt" data-fix="manual" onclick="selectFix(this)">手動追加（画像をドロップ）</button>
        </div>
        <div id="dropZone" class="drop-zone" style="display:none;">
            <div class="drop-zone-inner">
                <div class="drop-icon">📁</div>
                <p>画像をここにドラッグ&ドロップ</p>
                <p style="font-size:11px;color:#888;">JPG / PNG / WebP</p>
                <div id="dropPreview" style="margin-top:8px;"></div>
            </div>
        </div>
        <div class="modal-actions">
            <button class="btn-cancel" onclick="cancelNg()">Cancel</button>
            <button class="btn-submit-ng" id="submitNgBtn" onclick="submitNg()" disabled>NG送信</button>
        </div>
    </div>
</div>


<div class="done" id="doneScreen">
    <h2>Review Complete!</h2>
    <p id="doneStats"></p>
    <p>Results saved to panel_review.json</p>
    <p style="color:#555; margin-top:20px;">Close this window</p>
</div>

<script>
let panels = [];
let reviews = {};
let idx = 0;
let selectedFix = null;
let dragStartX = 0;
let dragging = false;
let uploadedFile = null;

let reviewerMode = 'horizontal';

async function init() {
    const [pr, rr, mr] = await Promise.all([fetch('/api/panels'), fetch('/api/reviews'), fetch('/api/mode')]);
    panels = await pr.json();
    reviews = await rr.json();
    const modeData = await mr.json();
    reviewerMode = modeData.mode || 'horizontal';
    if (reviewerMode === 'shorts') {
        document.body.classList.add('shorts-mode');
        document.querySelector('.topbar h1').textContent = 'Shorts Scene Review';
    }

    // Find first unreviewed (skip already OK'd panels, pending_recheck counts as unreviewed)
    let foundUnreviewed = false;
    for (let i = 0; i < panels.length; i++) {
        const r = reviews[panels[i].id];
        if (!r || r.status === 'pending_recheck') { idx = i; foundUnreviewed = true; break; }
    }
    // If all reviewed, show summary immediately
    if (!foundUnreviewed && panels.length > 0) {
        const okCount = Object.values(reviews).filter(r => r.status === 'ok').length;
        const ngCount = Object.values(reviews).filter(r => r.status === 'ng').length;
        if (okCount + ngCount >= panels.length) {
            // All done - show first panel but allow navigation
            idx = 0;
        }
    }

    buildDots();
    show(idx);
    updateStats();
    setupDrag();
}

function buildDots() {
    document.getElementById('dots').innerHTML = panels.map((_, i) =>
        '<div class="dot" onclick="goTo('+i+')"></div>'
    ).join('');
}

function show(i) {
    idx = i;
    const p = panels[i];
    const card = document.getElementById('card');
    card.className = 'card';
    card.style.transform = '';

    // Media
    const media = document.getElementById('media');
    const ext = (p.asset || '').split('.').pop().toLowerCase();
    let html = '';
    if (!p.asset_exists) {
        html = '<div class="missing">No asset<br>'+esc(p.asset)+'</div>';
    } else if (ext === 'mp4') {
        html = '<video src="/asset/'+encodeURI(p.asset)+'" autoplay loop muted playsinline></video>';
    } else {
        html = '<img src="/asset/'+encodeURI(p.asset)+'?t='+Date.now()+'" />';
    }
    html += '<span class="source-tag src-'+p.source+'">'+p.source+'</span>';
    media.innerHTML = html;
    watchMedia();

    // Info
    const info = document.getElementById('info');
    let scriptHtml = '';
    if (p.script_lines && p.script_lines.length > 0) {
        scriptHtml = p.script_lines.map(l => {
            const cls = (l.speaker||'').includes('\u30a8\u30a4\u30df\u30fc') ? 'spk-a' : 'spk-s';
            const lbl = (l.speaker||'').includes('\u30a8\u30a4\u30df\u30fc') ? '\u30a8\u30a4\u30df\u30fc' : '\u5c11\u5e74';
            return '<div class="script-line"><span class="spk '+cls+'">'+lbl+'</span>'+esc(l.text)+'</div>';
        }).join('');
    }
    const timingHtml = p.timing ? '<span class="timing-tag">'+esc(p.timing)+'</span>' : '';
    const metaHtml = reviewerMode === 'shorts'
        ? '<div class="card-meta">'+timingHtml+'</div>'
        : '<div class="card-meta">Seg '+p.segment_range[0]+'-'+p.segment_range[1]+' '+timingHtml+'</div>';
    const promptHtml = p.prompt ? '<div style="font-size:10px;color:#666;margin-top:6px;max-height:40px;overflow-y:auto;">Prompt: '+esc(p.prompt).substring(0,120)+'...</div>' : '';

    info.innerHTML =
        '<div class="card-title">'+(i+1)+'/'+panels.length+' '+esc(p.id)+'</div>' +
        metaHtml +
        '<div class="card-desc">'+esc(p.description)+'</div>' +
        (scriptHtml || '<div style="color:#666">No script text</div>') +
        promptHtml;

    // Badges reset
    document.getElementById('badgeOk').style.opacity = '0';
    document.getElementById('badgeNg').style.opacity = '0';

    // Dots
    document.querySelectorAll('.dot').forEach((d, j) => {
        d.className = 'dot';
        if (j === i) d.classList.add('current');
        const r = reviews[panels[j].id];
        if (r && r.status === 'ok') d.classList.add('ok');
        if (r && r.status === 'ng') d.classList.add('ng');
    });

    // Load suggested FX into sidebar for shorts mode
    if (reviewerMode === 'shorts' && document.getElementById('fxSidebar')) {
        loadSuggestedFx(p);
    }
}

let fxState = {};

function doOk() {
    const card = document.getElementById('card');
    document.getElementById('badgeOk').style.opacity = '1';
    card.classList.add('swipe-right');
    const p = panels[idx];

    if (reviewerMode === 'shorts') {
        // Collect FX settings from sidebar
        const effects = {};
        if (fxState.flash) effects.flash = true;
        if (fxState.shake) {
            effects.shake = true;
            effects.shake_intensity = parseInt(document.getElementById('fxShakeInt').value);
        }
        if (fxState.bounce_in) effects.bounce_in = true;
        if (fxState.rgb_shift) {
            effects.rgb_shift = true;
            effects.rgb_intensity = 3;
        }
        if (fxState.concentration_lines) effects.concentration_lines = true;

        const kb = { ken_burns: true };
        const kbDir = document.getElementById('kbDirection').value;
        if (kbDir !== 'auto') kb.kb_direction = kbDir;
        kb.kb_intensity = parseFloat(document.getElementById('kbIntensity').value);
        const fx_val = parseFloat(document.getElementById('kbFocusX').value);
        const fy_val = parseFloat(document.getElementById('kbFocusY').value);
        if (kbDir === 'zoom_in_center' && (fx_val !== 0.5 || fy_val !== 0.4)) {
            kb.kb_focus = [fx_val, fy_val];
        }

        const se = document.getElementById('seSelect').value;

        reviews[p.id] = {
            status: 'ok', comment: '', reviewed_at: new Date().toISOString(),
            effects: Object.keys(effects).length > 0 ? effects : undefined,
            ken_burns: kb,
            se: se !== 'none' ? se : undefined
        };
    } else {
        reviews[p.id] = { status: 'ok', comment: '', reviewed_at: new Date().toISOString() };
    }
    saveAndNext(p.id, reviews[p.id]);
}

function toggleFx(btn) {
    btn.classList.toggle('active');
    fxState[btn.dataset.fx] = btn.classList.contains('active');
}

function applyFxPreset(preset) {
    // Reset all
    fxState = { flash: false, shake: false, bounce_in: false, rgb_shift: false, concentration_lines: false };
    document.querySelectorAll('.fx-toggle').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.fx-preset').forEach(b => b.classList.remove('active-preset'));
    if (preset === 'calm') {
        document.getElementById('kbIntensity').value = 2.0;
        document.getElementById('kbIntVal').textContent = '2.0';
    } else if (preset === 'dramatic') {
        fxState.flash = true; fxState.shake = true;
        document.getElementById('fxShakeInt').value = 5;
        document.getElementById('fxShakeVal').textContent = '5';
        document.getElementById('kbIntensity').value = 3.0;
        document.getElementById('kbIntVal').textContent = '3.0';
    } else if (preset === 'impact') {
        fxState.flash = true; fxState.shake = true; fxState.rgb_shift = true;
        document.getElementById('fxShakeInt').value = 8;
        document.getElementById('fxShakeVal').textContent = '8';
        document.getElementById('kbIntensity').value = 3.5;
        document.getElementById('kbIntVal').textContent = '3.5';
    }
    // Update toggle buttons
    document.querySelectorAll('.fx-toggle').forEach(b => {
        if (fxState[b.dataset.fx]) b.classList.add('active');
    });
    // Highlight active preset
    document.querySelectorAll('.fx-preset').forEach(b => {
        if (b.textContent.toLowerCase().startsWith(preset)) b.classList.add('active-preset');
    });
}

function resetFxSidebar() {
    fxState = { flash: false, shake: false, bounce_in: false, rgb_shift: false, concentration_lines: false };
    document.querySelectorAll('.fx-toggle').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.fx-preset').forEach(b => b.classList.remove('active-preset'));
    document.getElementById('fxShakeInt').value = 6;
    document.getElementById('fxShakeVal').textContent = '6';
    document.getElementById('kbDirection').value = 'auto';
    document.getElementById('kbIntensity').value = 3.0;
    document.getElementById('kbIntVal').textContent = '3.0';
    document.getElementById('kbFocusX').value = 0.5;
    document.getElementById('kbFxVal').textContent = '0.5';
    document.getElementById('kbFocusY').value = 0.4;
    document.getElementById('kbFyVal').textContent = '0.4';
    document.getElementById('seSelect').value = 'none';
}

// === FX Preview Functions ===
let previewTimer = null;
function clearPreview() {
    const card = document.getElementById('card');
    card.className = 'card';
    // Remove any overlay
    const ov = card.querySelector('.fx-preview-overlay');
    if (ov) ov.remove();
    if (previewTimer) { clearTimeout(previewTimer); previewTimer = null; }
}

function previewFx(type) {
    clearPreview();
    const card = document.getElementById('card');
    if (type === 'flash') {
        const ov = document.createElement('div');
        ov.className = 'fx-preview-overlay preview-flash';
        card.querySelector('.card-media').appendChild(ov);
        previewTimer = setTimeout(() => { if (ov.parentNode) ov.remove(); }, 600);
    } else if (type === 'shake') {
        card.classList.add('preview-shake');
        previewTimer = setTimeout(clearPreview, 700);
    } else if (type === 'bounce') {
        card.classList.add('preview-bounce');
        previewTimer = setTimeout(clearPreview, 800);
    } else if (type === 'rgb') {
        card.classList.add('preview-rgb');
        previewTimer = setTimeout(clearPreview, 900);
    } else if (type === 'conc') {
        const ov = document.createElement('div');
        ov.className = 'fx-preview-overlay preview-conc-overlay';
        card.querySelector('.card-media').appendChild(ov);
        previewTimer = setTimeout(() => { if (ov.parentNode) ov.remove(); }, 1100);
    }
}

function previewKb() {
    clearPreview();
    const card = document.getElementById('card');
    const dir = document.getElementById('kbDirection').value;
    const d = dir === 'auto' ? 'zoom_in' : dir;
    card.classList.add('preview-kb', 'preview-kb-' + d);
    previewTimer = setTimeout(clearPreview, 1600);
}

// === SE Preview (Web Audio API synthesis) ===
let audioCtx = null;
function getAudioCtx() {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    return audioCtx;
}

function previewSe() {
    const se = document.getElementById('seSelect').value;
    if (se === 'none') return;
    const ctx = getAudioCtx();
    if (se === 'whoosh') {
        // Filtered noise sweep
        const dur = 0.4;
        const buf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
        const src = ctx.createBufferSource(); src.buffer = buf;
        const filt = ctx.createBiquadFilter(); filt.type = 'bandpass'; filt.frequency.setValueAtTime(200, ctx.currentTime);
        filt.frequency.exponentialRampToValueAtTime(4000, ctx.currentTime + dur * 0.4);
        filt.frequency.exponentialRampToValueAtTime(200, ctx.currentTime + dur);
        filt.Q.value = 2;
        const gain = ctx.createGain(); gain.gain.setValueAtTime(0.5, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + dur);
        src.connect(filt).connect(gain).connect(ctx.destination); src.start();
    } else if (se === 'impact') {
        // Low frequency thud
        const osc = ctx.createOscillator(); osc.frequency.setValueAtTime(150, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(40, ctx.currentTime + 0.15);
        const gain = ctx.createGain(); gain.gain.setValueAtTime(0.8, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.2);
        const dist = ctx.createWaveshaper ? null : null;
        osc.connect(gain).connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime + 0.25);
        // Add noise burst
        const dur = 0.1;
        const buf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
        const d = buf.getChannelData(0);
        for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
        const ns = ctx.createBufferSource(); ns.buffer = buf;
        const ng = ctx.createGain(); ng.gain.setValueAtTime(0.4, ctx.currentTime);
        ng.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + dur);
        ns.connect(ng).connect(ctx.destination); ns.start();
    } else if (se === 'surprise') {
        // Quick ascending tone
        const osc = ctx.createOscillator(); osc.type = 'sine';
        osc.frequency.setValueAtTime(400, ctx.currentTime);
        osc.frequency.exponentialRampToValueAtTime(1200, ctx.currentTime + 0.15);
        osc.frequency.exponentialRampToValueAtTime(800, ctx.currentTime + 0.3);
        const gain = ctx.createGain(); gain.gain.setValueAtTime(0.4, ctx.currentTime);
        gain.gain.setValueAtTime(0.4, ctx.currentTime + 0.15);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.35);
        osc.connect(gain).connect(ctx.destination); osc.start(); osc.stop(ctx.currentTime + 0.4);
    } else if (se === 'tension') {
        // Low drone with slight wobble
        const osc = ctx.createOscillator(); osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(60, ctx.currentTime);
        const lfo = ctx.createOscillator(); lfo.frequency.value = 3;
        const lfoGain = ctx.createGain(); lfoGain.gain.value = 8;
        lfo.connect(lfoGain).connect(osc.frequency);
        const gain = ctx.createGain(); gain.gain.setValueAtTime(0.0, ctx.currentTime);
        gain.gain.linearRampToValueAtTime(0.3, ctx.currentTime + 0.2);
        gain.gain.setValueAtTime(0.3, ctx.currentTime + 0.6);
        gain.gain.linearRampToValueAtTime(0.0, ctx.currentTime + 1.0);
        const filt = ctx.createBiquadFilter(); filt.type = 'lowpass'; filt.frequency.value = 200;
        osc.connect(filt).connect(gain).connect(ctx.destination);
        osc.start(); lfo.start(); osc.stop(ctx.currentTime + 1.1); lfo.stop(ctx.currentTime + 1.1);
    }
}

function loadSuggestedFx(p) {
    resetFxSidebar();
    const sfx = p.suggested_fx;
    if (!sfx) return;

    // Load effects
    if (sfx.effects) {
        Object.keys(sfx.effects).forEach(key => {
            if (key === 'shake_intensity' || key === 'rgb_intensity') return;
            if (sfx.effects[key]) {
                fxState[key] = true;
                const btn = document.querySelector('.fx-toggle[data-fx="'+key+'"]');
                if (btn) btn.classList.add('active');
            }
        });
        if (sfx.effects.shake_intensity) {
            document.getElementById('fxShakeInt').value = sfx.effects.shake_intensity;
            document.getElementById('fxShakeVal').textContent = sfx.effects.shake_intensity;
        }
    }

    // Load KB
    if (sfx.ken_burns) {
        const kb = sfx.ken_burns;
        if (kb.kb_direction) {
            document.getElementById('kbDirection').value = kb.kb_direction;
        }
        if (kb.kb_intensity != null) {
            document.getElementById('kbIntensity').value = kb.kb_intensity;
            document.getElementById('kbIntVal').textContent = kb.kb_intensity;
        }
        if (kb.kb_focus) {
            document.getElementById('kbFocusX').value = kb.kb_focus[0];
            document.getElementById('kbFxVal').textContent = kb.kb_focus[0];
            document.getElementById('kbFocusY').value = kb.kb_focus[1];
            document.getElementById('kbFyVal').textContent = kb.kb_focus[1];
        }
    }

    // Load SE
    if (sfx.se) {
        document.getElementById('seSelect').value = sfx.se;
    }
}

function doNg() {
    selectedFix = null;
    uploadedFile = null;
    document.getElementById('ngComment').value = '';
    document.querySelectorAll('.fix-opt').forEach(b => b.classList.remove('selected'));
    document.getElementById('submitNgBtn').disabled = true;
    document.getElementById('dropZone').style.display = 'none';
    document.getElementById('dropPreview').innerHTML = '';

    // Update fix options based on mode
    const fixOpts = document.querySelector('.fix-options');
    if (reviewerMode === 'shorts') {
        fixOpts.innerHTML =
            '<button class="fix-opt" data-fix="regenerate" onclick="selectFix(this)">再生成（同じプロンプトでリトライ）</button>' +
            '<button class="fix-opt" data-fix="change_prompt" onclick="selectFix(this)">プロンプト変更（コメントに新プロンプト記載）</button>' +
            '<button class="fix-opt" data-fix="manual" onclick="selectFix(this)">手動追加（画像をドロップ）</button>';
    }

    document.getElementById('ngModal').classList.add('active');
    document.getElementById('ngComment').focus();
}

function selectFix(btn) {
    document.querySelectorAll('.fix-opt').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    selectedFix = btn.dataset.fix;
    // Show drop zone for manual fix
    const dz = document.getElementById('dropZone');
    if (selectedFix === 'manual') {
        dz.style.display = 'block';
        setupDropZone();
    } else {
        dz.style.display = 'none';
        uploadedFile = null;
    }
    // Update button state (check both comment and selectedFix)
    document.getElementById('submitNgBtn').disabled =
        !document.getElementById('ngComment').value.trim() || !selectedFix;
}

function setupDropZone() {
    const dz = document.getElementById('dropZone');
    if (dz._setup) return;
    dz._setup = true;
    dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
    dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
    dz.addEventListener('drop', async e => {
        e.preventDefault();
        dz.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (!file || !file.type.startsWith('image/')) return;
        uploadedFile = file;
        // Preview
        const reader = new FileReader();
        reader.onload = ev => {
            document.getElementById('dropPreview').innerHTML =
                '<img src="'+ev.target.result+'" /><div class="uploaded-name">'+esc(file.name)+'</div>';
        };
        reader.readAsDataURL(file);
        // Update button state after file is uploaded
        document.getElementById('submitNgBtn').disabled =
            !document.getElementById('ngComment').value.trim() || !selectedFix;
    });
    // Click to browse
    dz.addEventListener('click', () => {
        const inp = document.createElement('input');
        inp.type = 'file';
        inp.accept = 'image/*';
        inp.onchange = () => {
            if (inp.files[0]) {
                uploadedFile = inp.files[0];
                const reader = new FileReader();
                reader.onload = ev => {
                    document.getElementById('dropPreview').innerHTML =
                        '<img src="'+ev.target.result+'" /><div class="uploaded-name">'+esc(inp.files[0].name)+'</div>';
                };
                reader.readAsDataURL(inp.files[0]);
                // Update button state after file is selected
                document.getElementById('submitNgBtn').disabled =
                    !document.getElementById('ngComment').value.trim() || !selectedFix;
            }
        };
        inp.click();
    });
}

function cancelNg() {
    document.getElementById('ngModal').classList.remove('active');
}

async function submitNg() {
    const comment = document.getElementById('ngComment').value.trim();
    if (!comment || !selectedFix) return;

    const p = panels[idx];

    // Upload file if manual fix with file
    if (selectedFix === 'manual' && uploadedFile) {
        const formData = new FormData();
        formData.append('file', uploadedFile);
        formData.append('panel_id', p.id);
        await fetch('/api/upload', { method: 'POST', body: formData });
    }

    document.getElementById('ngModal').classList.remove('active');
    const card = document.getElementById('card');
    document.getElementById('badgeNg').style.opacity = '1';
    card.classList.add('swipe-left');

    reviews[p.id] = {
        status: 'ng', comment: comment, fix_method: selectedFix,
        uploaded: !!(selectedFix === 'manual' && uploadedFile),
        reviewed_at: new Date().toISOString()
    };
    uploadedFile = null;
    document.getElementById('dropPreview').innerHTML = '';
    saveAndNext(p.id, reviews[p.id]);
}

async function saveAndNext(panelId, data) {
    await fetch('/api/save_review', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ panel_id: panelId, ...data })
    });
    updateStats();
    setTimeout(() => {
        if (idx < panels.length - 1) {
            show(idx + 1);
        } else {
            finish();
        }
    }, 300);
}

function doUndo() {
    if (idx > 0) {
        idx--;
        const p = panels[idx];
        delete reviews[p.id];
        fetch('/api/save_review', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ panel_id: p.id, status: 'undo' })
        });
        show(idx);
        updateStats();
    }
}

function goTo(i) { show(i); }

function updateStats() {
    const ok = Object.values(reviews).filter(r => r.status === 'ok').length;
    const ng = Object.values(reviews).filter(r => r.status === 'ng').length;
    const rem = panels.length - ok - ng;
    document.getElementById('cOk').textContent = ok;
    document.getElementById('cNg').textContent = ng;
    document.getElementById('cRem').textContent = rem + ' remaining';
    document.getElementById('pBar').style.width = Math.round((ok + ng) / panels.length * 100) + '%';
}

async function finish() {
    await fetch('/api/finish', { method: 'POST' });
    const ok = Object.values(reviews).filter(r => r.status === 'ok').length;
    const ng = Object.values(reviews).filter(r => r.status === 'ng').length;
    document.getElementById('app').style.display = 'none';
    const done = document.getElementById('doneScreen');
    done.style.display = 'flex';
    document.getElementById('doneStats').textContent = 'OK: '+ok+' / NG: '+ng+' / Skip: '+(panels.length-ok-ng);
}

function setupDrag() {
    const card = document.getElementById('card');
    let startX = 0;

    card.addEventListener('mousedown', e => { startX = e.clientX; dragging = true; card.classList.add('swiping'); });
    document.addEventListener('mousemove', e => {
        if (!dragging) return;
        const dx = e.clientX - startX;
        card.style.transform = 'translateX('+dx+'px) rotate('+(dx*0.05)+'deg)';
        document.getElementById('badgeOk').style.opacity = Math.min(1, Math.max(0, dx / 100));
        document.getElementById('badgeNg').style.opacity = Math.min(1, Math.max(0, -dx / 100));
    });
    document.addEventListener('mouseup', e => {
        if (!dragging) return;
        dragging = false;
        card.classList.remove('swiping');
        const dx = e.clientX - startX;
        if (dx > 100) { doOk(); }
        else if (dx < -100) { doNg(); }
        else { card.style.transform = ''; document.getElementById('badgeOk').style.opacity='0'; document.getElementById('badgeNg').style.opacity='0'; }
    });

    // Touch
    card.addEventListener('touchstart', e => { startX = e.touches[0].clientX; dragging = true; card.classList.add('swiping'); });
    document.addEventListener('touchmove', e => {
        if (!dragging) return;
        const dx = e.touches[0].clientX - startX;
        card.style.transform = 'translateX('+dx+'px) rotate('+(dx*0.05)+'deg)';
        document.getElementById('badgeOk').style.opacity = Math.min(1, Math.max(0, dx / 100));
        document.getElementById('badgeNg').style.opacity = Math.min(1, Math.max(0, -dx / 100));
    });
    document.addEventListener('touchend', e => {
        if (!dragging) return;
        dragging = false;
        card.classList.remove('swiping');
        const dx = e.changedTouches[0].clientX - startX;
        if (dx > 100) { doOk(); }
        else if (dx < -100) { doNg(); }
        else { card.style.transform = ''; document.getElementById('badgeOk').style.opacity='0'; document.getElementById('badgeNg').style.opacity='0'; }
    });
}

document.addEventListener('keydown', e => {
    if (document.getElementById('ngModal').classList.contains('active')) {
        if (e.key === 'Escape') cancelNg();
        return;
    }
    if (e.key === 'ArrowRight') doOk();
    if (e.key === 'ArrowLeft') doNg();
    if (e.key === 'u' || e.key === 'U') doUndo();
});

// Enable submit when comment has text and fix is selected
document.getElementById('ngComment').addEventListener('input', () => {
    document.getElementById('submitNgBtn').disabled =
        !document.getElementById('ngComment').value.trim() || !selectedFix;
});

// Auto-retry failed media after show()
function watchMedia() {
    const media = document.getElementById('media');
    const img = media.querySelector('img');
    const vid = media.querySelector('video');
    if (img) {
        img.onerror = function() {
            if (!this._retried) {
                this._retried = true;
                this.src = this.src.split('?')[0] + '?retry=' + Date.now();
            } else {
                this.outerHTML = '<div class="missing" style="color:#f44336">Load failed<br><button onclick="show(idx)" style="margin-top:8px;padding:6px 16px;background:#1A73E8;color:#fff;border:none;border-radius:6px;cursor:pointer">Retry</button></div>';
            }
        };
    }
    if (vid) {
        vid.onerror = function() {
            if (!this._retried) {
                this._retried = true;
                this.src = this.src.split('?')[0] + '?retry=' + Date.now();
                this.load();
            }
        };
    }
}

function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

init();
</script>
</body>
</html>"""


class ReviewHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        try:
            if self.path == "/" or self.path == "/index.html":
                html = build_html()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))
            elif self.path == "/api/panels":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(server_state["panels"], ensure_ascii=False).encode("utf-8"))
            elif self.path == "/api/mode":
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"mode": REVIEWER_MODE}).encode("utf-8"))
            elif self.path == "/api/reviews":
                review_data = load_review()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(review_data, ensure_ascii=False).encode("utf-8"))
            elif self.path.startswith("/asset/"):
                import random
                from urllib.parse import unquote
                asset_rel = unquote(self.path[7:].split("?")[0])  # URL decode + remove query params
                asset_path = PROJECT_ROOT / asset_rel
                # If path is a directory, pick a random image from it
                if asset_path.is_dir():
                    img_exts = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
                    candidates = [f for f in asset_path.iterdir()
                                  if f.is_file() and f.suffix.lower() in img_exts]
                    if candidates:
                        asset_path = random.choice(candidates)
                    else:
                        self.send_error(404, "No images in directory")
                        return
                if asset_path.exists():
                    try:
                        with open(asset_path, "rb") as f:
                            file_data = f.read()
                        ext = asset_path.suffix.lower()
                        content_types = {
                            ".png": "image/png", ".jpg": "image/jpeg",
                            ".jpeg": "image/jpeg", ".webp": "image/webp",
                            ".avif": "image/avif",
                            ".mp4": "video/mp4",
                        }
                        ct = content_types.get(ext, "application/octet-stream")
                        self.send_response(200)
                        self.send_header("Content-Type", ct)
                        self.send_header("Content-Length", str(len(file_data)))
                        self.send_header("Cache-Control", "no-cache")
                        self.end_headers()
                        self.wfile.write(file_data)
                    except Exception as e:
                        print(f"  ERROR serving {asset_path}: {e}")
                        self.send_error(500, f"Error reading file: {e}")
                else:
                    print(f"  404 NOT FOUND: {asset_path}")
                    self.send_error(404, f"Not found: {asset_rel}")
            else:
                self.send_error(404)
        except (BrokenPipeError, ConnectionResetError):
            # Browser closed connection - this is normal, ignore silently
            pass

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))

        if self.path == "/api/upload":
            # Parse multipart form data for file upload (Python 3.14 compatible)
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" in content_type:
                import email.parser
                import io

                # Parse multipart data manually
                boundary = content_type.split("boundary=")[1].encode()
                body = self.rfile.read(content_length)

                # Simple multipart parser
                parts = body.split(b'--' + boundary)
                panel_id = "uploaded"
                file_data = None
                filename = None

                for part in parts:
                    if b'name="panel_id"' in part:
                        panel_id = part.split(b'\r\n\r\n')[1].split(b'\r\n')[0].decode('utf-8', errors='ignore')
                    elif b'name="file"' in part and b'filename=' in part:
                        # Extract filename
                        header_end = part.find(b'\r\n\r\n')
                        if header_end > 0:
                            headers = part[:header_end].decode('utf-8', errors='ignore')
                            for line in headers.split('\r\n'):
                                if 'filename=' in line:
                                    filename = line.split('filename="')[1].split('"')[0]
                                    break
                            file_data = part[header_end+4:]
                            # Remove trailing boundary
                            if file_data.endswith(b'\r\n'):
                                file_data = file_data[:-2]

                if file_data and filename:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
                        ext = ".jpg"
                    save_name = f"{panel_id}{ext}"
                    save_path = PROJECT_ROOT / "assets" / "panels" / save_name
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(file_data)
                    print(f"  UPLOAD: {save_name} ({save_path.stat().st_size // 1024}KB)")

                    # Update image_map.json with new asset
                    image_map_path = PROJECT_ROOT / "image_map.json"
                    if image_map_path.exists():
                        with open(image_map_path, "r", encoding="utf-8") as f:
                            img_map = json.load(f)
                        for p in img_map.get("panels", []):
                            if p["id"] == panel_id:
                                p["asset"] = f"assets/panels/{save_name}"
                                p["source"] = "manual_upload"
                                break
                        with open(image_map_path, "w", encoding="utf-8") as f:
                            json.dump(img_map, f, ensure_ascii=False, indent=2)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "file": save_name}).encode("utf-8"))
                return
            self.send_error(400)
            return

        body = self.rfile.read(content_length)
        data = json.loads(body) if body else {}

        if self.path == "/api/save_review":
            review_data = load_review()
            panel_id = data.pop("panel_id", "")
            if panel_id:
                if data.get("status") == "undo":
                    review_data.pop(panel_id, None)
                    print(f"  UNDO: {panel_id}")
                else:
                    review_data[panel_id] = data
                    fix = data.get("fix_method", "")
                    print(f"  {data.get('status','?').upper():3s} {panel_id} {('['+fix+'] ' if fix else '')}{data.get('comment','')[:50]}")
                save_review(review_data)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        elif self.path == "/api/finish":
            server_state["done"] = True
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        else:
            self.send_error(404)


def main():
    global REVIEWER_MODE, REVIEW_FILE

    # Shorts mode
    shorts_mode = "--shorts" in sys.argv
    if shorts_mode:
        REVIEWER_MODE = "shorts"
        shorts_idx = sys.argv.index("--shorts")
        if shorts_idx + 1 < len(sys.argv):
            scenes_json = sys.argv[shorts_idx + 1]
        else:
            print("Error: --shorts requires <scenes.json> path")
            sys.exit(1)
        # Set review file to same directory as scenes.json
        scenes_dir = Path(scenes_json).parent
        REVIEW_FILE = scenes_dir / "scene_review.json"
        panels = load_shorts_data(scenes_json)
    else:
        manifest_path = None
        args = [a for a in sys.argv[1:] if a not in ("--recheck",)]
        if args:
            manifest_path = args[0]
        else:
            output_dir = PROJECT_ROOT / "output"
            if output_dir.exists():
                for d in sorted(output_dir.iterdir(), reverse=True):
                    mp = d / "audio" / "audio_manifest.json"
                    if mp.exists():
                        manifest_path = str(mp)
                        break
        panels = load_data(manifest_path)

    recheck_mode = "--recheck" in sys.argv

    if recheck_mode:
        existing = load_review()
        recheck_ids = {pid for pid, rv in existing.items()
                       if rv.get("status") == "pending_recheck"}
        panels = [p for p in panels if p["id"] in recheck_ids]
        if not panels:
            print("No panels pending recheck.")
            return True
        print(f"Recheck mode: {len(panels)} panels to re-review")

    server_state["panels"] = panels

    existing = load_review()
    reviewed = sum(1 for p in panels if p["id"] in existing
                   and existing[p["id"]].get("status") in ("ok", "ng"))

    port = 8766

    class ReusableHTTPServer(http.server.HTTPServer):
        allow_reuse_address = True

    server = ReusableHTTPServer(("127.0.0.1", port), ReviewHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    print(f"\nPanel Review (Tinder): {url}")
    print(f"  Panels: {len(panels)}")
    print(f"  Reviewed: {reviewed}")
    print(f"  Save: {REVIEW_FILE}")
    print(f"  Opening browser...\n")

    webbrowser.open(url)

    while not server_state["done"]:
        time.sleep(0.5)

    server.shutdown()

    review_data = load_review()
    ok = sum(1 for v in review_data.values() if v.get("status") == "ok")
    ng = sum(1 for v in review_data.values() if v.get("status") == "ng")

    print(f"\nReview complete!")
    print(f"  OK: {ok} / NG: {ng} / Skip: {len(panels) - ok - ng}")

    if ng > 0:
        print(f"\nNG panels:")
        for pid, rv in review_data.items():
            if rv.get("status") == "ng":
                fix = rv.get("fix_method", "?")
                print(f"  [{pid}] [{fix}] {rv.get('comment', '')}")

    return ng == 0


if __name__ == "__main__":
    main()
