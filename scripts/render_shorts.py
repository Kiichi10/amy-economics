#!/usr/bin/env python3
"""
Shorts縦動画レンダラー（1080x1920）

パターン1: letterbox — 上下黒バー+テロップ、中央に16:9コンテンツ
パターン2: native_vertical — 9:16ネイティブ画像 + 中央字幕（背景なし）

使い方:
  python3 render_shorts.py <render_plan.json> --silent
"""

import json
import os
import re
import subprocess
import time
from pathlib import Path

import math
import random

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).parent.parent

_static_cache = {}
_subtitle_cache = {}
_kb_src_cache = {}
_video_cache = {}  # asset_path -> { "cap": VideoCapture, "fps": float, "frames": {int: ndarray} }
_KB_DIRECTIONS = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in_center"]
_VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.webm'}


# ============================================================
# 画像処理
# ============================================================
def crop_fit(img, box_w, box_h):
    h, w = img.shape[:2]
    r_img, r_box = w / h, box_w / box_h
    if r_img > r_box:
        nw, nh = int(box_h * r_img), box_h
    else:
        nw, nh = box_w, int(box_w / r_img)
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    x, y = (nw - box_w) // 2, (nh - box_h) // 2
    return resized[y:y + box_h, x:x + box_w].copy()


def _is_video_asset(asset_path):
    """アセットが動画ファイルかどうか判定"""
    return Path(asset_path).suffix.lower() in _VIDEO_EXTS


def get_video_frame(asset_path, width, height, elapsed_sec, event_duration):
    """動画アセットから指定時刻のフレームを取得（crop_fitでリサイズ）"""
    full = str(PROJECT_ROOT / asset_path)

    if asset_path not in _video_cache:
        cap = cv2.VideoCapture(full)
        if not cap.isOpened():
            print(f"  ⚠️ 動画を開けません: {full}")
            return np.zeros((height, width, 3), dtype=np.uint8)
        vfps = cap.get(cv2.CAP_PROP_FPS) or 24
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_duration = total_frames / vfps
        _video_cache[asset_path] = {
            "cap": cap, "fps": vfps, "frames": {},
            "total_frames": total_frames, "video_duration": video_duration
        }

    vc = _video_cache[asset_path]
    cap, vfps = vc["cap"], vc["fps"]
    video_dur = vc["video_duration"]

    # イベント尺に対して動画尺をマッピング（動画が短ければ速度調整せずループ/最終フレーム固定）
    t = min(elapsed_sec, video_dur - 0.01)
    if t < 0:
        t = 0
    frame_idx = int(t * vfps)
    frame_idx = min(frame_idx, vc["total_frames"] - 1)

    # キャッシュ済みフレームがあればそれを使う
    cache_key = f"{frame_idx}_{width}_{height}"
    if cache_key in vc["frames"]:
        return vc["frames"][cache_key]

    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret or frame is None:
        return np.zeros((height, width, 3), dtype=np.uint8)

    result = crop_fit(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), width, height)
    vc["frames"][cache_key] = result
    return result


def get_static_image(asset_path, width, height):
    key = f"{asset_path}_{width}_{height}"
    if key in _static_cache:
        return _static_cache[key]
    full = PROJECT_ROOT / asset_path
    if not full.exists():
        r = np.zeros((height, width, 3), dtype=np.uint8)
    else:
        img = cv2.imread(str(full))
        if img is None:
            r = np.zeros((height, width, 3), dtype=np.uint8)
        else:
            r = crop_fit(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), width, height)
    _static_cache[key] = r
    return r


# ============================================================
# Ken Burns
# ============================================================
def apply_ken_burns(asset_path, box_w, box_h, progress, kb_index=0, intensity=1.0, focus=None):
    """Ken Burnsエフェクト。focus=[fx, fy] で焦点を指定（0.0-1.0）"""
    ZR, PR = 0.06 * intensity, 0.04 * intensity
    sb = 1.0 + ZR
    key = f"{asset_path}_kb_{box_w}_{box_h}"
    if key not in _kb_src_cache:
        full = PROJECT_ROOT / asset_path
        if not full.exists():
            return np.zeros((box_h, box_w, 3), dtype=np.uint8)
        img = cv2.imread(str(full))
        if img is None:
            return np.zeros((box_h, box_w, 3), dtype=np.uint8)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        _kb_src_cache[key] = crop_fit(img, int(box_w * sb), int(box_h * sb))
    src = _kb_src_cache[key]
    oh, ow = src.shape[:2]
    t = progress * progress * (3.0 - 2.0 * progress)
    d = _KB_DIRECTIONS[kb_index % len(_KB_DIRECTIONS)]
    if d == "zoom_in_center":
        z = 1 + ZR * t
        cw, ch = box_w * sb / z, box_h * sb / z
        if focus:
            # 焦点座標（src内の比率）
            fx, fy = focus
            target_x, target_y = ow * fx, oh * fy
            # t=0: 画像中央、t=1: 焦点に収束
            cx_center, cy_center = (ow - cw) / 2, (oh - ch) / 2
            cx_focus = target_x - cw / 2
            cy_focus = target_y - ch / 2
            cx = cx_center + (cx_focus - cx_center) * t
            cy = cy_center + (cy_focus - cy_center) * t
        else:
            cx, cy = (ow - cw) / 2, (oh - ch) / 2
        cx = max(0, min(cx, ow - cw))
        cy = max(0, min(cy, oh - ch))
        return cv2.resize(src[int(cy):int(cy + ch), int(cx):int(cx + cw)],
                          (box_w, box_h), interpolation=cv2.INTER_LINEAR)
    elif d == "zoom_in":
        z, px, py = 1 + ZR * t, PR * t * box_w, PR * t * .5 * box_h
    elif d == "zoom_out":
        z, px, py = 1 + ZR * (1 - t), PR * (1 - t) * box_w, PR * (1 - t) * .5 * box_h
    elif d == "pan_left":
        z, px, py = 1 + ZR * .5, PR * (1 - t) * box_w, 0
    else:
        z, px, py = 1 + ZR * .5, PR * t * box_w, 0
    cw, ch = box_w * sb / z, box_h * sb / z
    cx = max(0, min((ow - cw) / 2 + px, ow - cw))
    cy = max(0, min((oh - ch) / 2 + py, oh - ch))
    return cv2.resize(src[int(cy):int(cy + ch), int(cx):int(cx + cw)],
                      (box_w, box_h), interpolation=cv2.INTER_LINEAR)


# ============================================================
# テキスト共通
# ============================================================
def _wrap_text(text, font, max_width, draw):
    # 末尾句読点を除去（孤立行防止 — case_study 2026-03-03 L4）
    text = text.rstrip('。？！?!')
    # 「、」だけが次行に残るのを防ぐため、行末「、」も除去対象に
    lines, cur = [], ""
    for ch in text:
        t = cur + ch
        if draw.textbbox((0, 0), t, font=font)[2] > max_width and cur:
            # 句読点・助詞で自然な改行ポイントを探す（case_study 2026-03-03 L3）
            break_chars = '、。？！?!）」』】〉》'
            particle_chars = 'はがをにでともへやかの'
            best = -1
            half = len(cur) // 2
            # 後半から句読点を探す（最優先）
            for i in range(len(cur) - 1, half - 1, -1):
                if cur[i] in break_chars:
                    best = i + 1
                    break
            # 句読点なければ助詞を探す
            if best < 0:
                for i in range(len(cur) - 1, half - 1, -1):
                    if cur[i] in particle_chars:
                        best = i + 1
                        break
            if best > 0 and best < len(cur):
                lines.append(cur[:best])
                cur = cur[best:] + ch
            else:
                lines.append(cur)
                cur = ch
        else:
            cur = t
    if cur:
        # 最終行が「、」や「。」だけにならないよう、1文字なら前行にマージ
        if len(cur) <= 1 and lines:
            lines[-1] += cur
        else:
            lines.append(cur)
    return lines


def _parse_colored_text(text):
    """色タグ・サイズタグ付きテキストをパース。
    フォーマット: {color:text}, {color_big:text}, {big:text}
    戻り値: [(text, color_rgb, scale), ...]  scale=1.0が通常、1.3がbig
    """
    parts, last = [], 0
    color_map = {
        'yellow': (255, 255, 0), 'red': (255, 60, 60), 'cyan': (0, 220, 255),
        'green': (100, 255, 100), 'orange': (255, 180, 0), 'white': (255, 255, 255),
    }
    for m in re.finditer(r'\{([\w_]+):([^}]+)\}', text):
        if m.start() > last:
            parts.append((text[last:m.start()], (255, 255, 255), 1.0))
        tag = m.group(1)
        # big修飾子の判定
        scale = 1.0
        if tag.endswith('_big'):
            scale = 1.3
            tag = tag[:-4]  # "red_big" → "red"
        elif tag == 'big':
            scale = 1.3
            tag = 'white'
        color = color_map.get(tag, (255, 255, 255))
        parts.append((m.group(2), color, scale))
        last = m.end()
    if last < len(text):
        parts.append((text[last:], (255, 255, 255), 1.0))
    return parts


def _draw_outlined(draw, x, y, text, font, fill, outline_w=8):
    """黒縁取り付きテキスト"""
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if dx * dx + dy * dy <= outline_w * outline_w:
                draw.text((x + dx, y + dy), text, fill=(0, 0, 0, 255), font=font)
    c = (*fill, 255) if len(fill) == 3 else fill
    draw.text((x, y), text, fill=c, font=font)


def _draw_colored_lines(draw, lines_plain, parts, font, canvas_w, y_start,
                        line_spacing, outline_w, char_offset=0,
                        base_font_size=None):
    """色付き・サイズ混在テキストを行ごとに中央揃えで描画"""
    y = y_start
    ci = char_offset
    font_path = "/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc"
    if base_font_size is None:
        base_font_size = font.size if hasattr(font, 'size') else 84
    _font_cache = {}

    def get_font(scale):
        if scale not in _font_cache:
            sz = int(base_font_size * scale)
            try:
                _font_cache[scale] = ImageFont.truetype(font_path, sz)
            except Exception:
                _font_cache[scale] = font
        return _font_cache[scale]

    for line in lines_plain:
        # この行に対応するpartsセグメントを抽出
        segs, rem, skip = [], len(line), ci
        for part in parts:
            pt, pc = part[0], part[1]
            ps = part[2] if len(part) > 2 else 1.0
            if skip > 0:
                if skip >= len(pt):
                    skip -= len(pt)
                    continue
                pt = pt[skip:]
                skip = 0
            take = min(len(pt), rem)
            if take > 0:
                segs.append((pt[:take], pc, ps))
                rem -= take
            if rem <= 0:
                break
        # 行幅計算（サイズ混在対応）
        lw = 0
        for st, sc, ss in segs:
            f = get_font(ss)
            lw += draw.textbbox((0, 0), st, font=f)[2]
        x = (canvas_w - lw) // 2
        # ベースライン揃え描画
        line_h = draw.textbbox((0, 0), line, font=font)[3]
        for st, sc, ss in segs:
            f = get_font(ss)
            seg_h = draw.textbbox((0, 0), st, font=f)[3]
            # bigテキストは上にはみ出す形でベースライン揃え
            y_offset = (line_h - seg_h) if ss > 1.0 else 0
            _draw_outlined(draw, x, y + y_offset, st, f, sc, outline_w)
            x += draw.textbbox((0, 0), st, font=f)[2]
        ci += len(line)
        y += line_spacing
    return ci


def alpha_blend(canvas, rgba, x, y):
    oh, ow = rgba.shape[:2]
    ch, cw = canvas.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(cw, x + ow), min(ch, y + oh)
    if x2 <= x1 or y2 <= y1:
        return
    ox1, oy1 = x1 - x, y1 - y
    sl = rgba[oy1:oy1 + y2 - y1, ox1:ox1 + x2 - x1]
    a = sl[:, :, 3:4].astype(np.float32) / 255.0
    roi = canvas[y1:y2, x1:x2].astype(np.float32)
    canvas[y1:y2, x1:x2] = (sl[:, :, :3].astype(np.float32) * a + roi * (1 - a)).astype(np.uint8)


# ============================================================
# 集中線エフェクト
# ============================================================
_concentration_cache = {}


def _render_concentration_lines(width, height, seed=42):
    """半透明の集中線オーバーレイ（RGBA）を生成"""
    key = (width, height, seed)
    if key in _concentration_cache:
        return _concentration_cache[key]
    panel = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    cx, cy = width // 2, height // 2
    rng = random.Random(seed)
    diag = math.sqrt(cx * cx + cy * cy) * 1.2
    num_lines = 80
    for _ in range(num_lines):
        angle = rng.uniform(0, 2 * math.pi)
        # 太い三角形の線を中心から外に向けて描画
        r_inner = rng.uniform(diag * 0.35, diag * 0.50)
        r_outer = diag
        w_inner = rng.uniform(1, 3)
        w_outer = rng.uniform(15, 45)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        # 三角形の4頂点
        perp_cos, perp_sin = -sin_a, cos_a
        p1 = (cx + cos_a * r_inner + perp_cos * w_inner,
              cy + sin_a * r_inner + perp_sin * w_inner)
        p2 = (cx + cos_a * r_inner - perp_cos * w_inner,
              cy + sin_a * r_inner - perp_sin * w_inner)
        p3 = (cx + cos_a * r_outer - perp_cos * w_outer,
              cy + sin_a * r_outer - perp_sin * w_outer)
        p4 = (cx + cos_a * r_outer + perp_cos * w_outer,
              cy + sin_a * r_outer + perp_sin * w_outer)
        alpha = rng.randint(60, 140)
        draw.polygon([p1, p2, p3, p4], fill=(255, 255, 255, alpha))
    result = np.array(panel, dtype=np.uint8)
    _concentration_cache[key] = result
    return result


# ============================================================
# シーンエフェクト
# ============================================================
def _apply_camera_shake(canvas, elapsed, intensity=8):
    """カメラシェイク: sin波ベースの微小振動"""
    freq = 25.0  # 振動周波数
    dx = int(intensity * math.sin(elapsed * freq * 2 * math.pi))
    dy = int(intensity * math.cos(elapsed * freq * 1.7 * math.pi + 0.5))
    h, w = canvas.shape[:2]
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(canvas, M, (w, h), borderMode=cv2.BORDER_REPLICATE)


def _apply_flash(canvas, elapsed, duration=0.15):
    """フラッシュ: シーン冒頭の白フラッシュ（フェードアウト）"""
    if elapsed > duration:
        return canvas
    alpha = 1.0 - (elapsed / duration)
    white = np.full_like(canvas, 255)
    return cv2.addWeighted(canvas, 1.0 - alpha * 0.8, white, alpha * 0.8, 0)


def _apply_bounce_in(canvas, content_y, content_h, elapsed, duration=0.3):
    """バウンスイン: コンテンツが上からバウンドして登場"""
    if elapsed > duration:
        return canvas
    t = elapsed / duration
    # ease-out bounce
    bounce = abs(math.sin(t * math.pi * 2.5)) * (1.0 - t) * 0.08
    offset_y = int(-content_h * (1.0 - t) * 0.05 + content_h * bounce)
    if offset_y == 0:
        return canvas
    result = canvas.copy()
    # コンテンツ領域を上下にシフト
    if offset_y > 0:
        result[content_y + offset_y:content_y + content_h] = canvas[content_y:content_y + content_h - offset_y]
        result[content_y:content_y + offset_y] = 0
    return result


def _apply_subtitle_shake(sub_rgba, elapsed, intensity=4):
    """テキストシェイク: 字幕の微小振動（怒り/叫び表現）"""
    freq = 30.0
    dx = int(intensity * math.sin(elapsed * freq * 2 * math.pi))
    dy = int(intensity * math.cos(elapsed * freq * 2.3 * math.pi))
    h, w = sub_rgba.shape[:2]
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(sub_rgba, M, (w, h), borderMode=cv2.BORDER_CONSTANT,
                          borderValue=(0, 0, 0, 0))


def _apply_rgb_shift(canvas, elapsed, intensity=5):
    """RGBシフト: チャンネルをずらしてグリッチ感"""
    dx = int(intensity * math.sin(elapsed * 15))
    r, g, b = canvas[:, :, 0], canvas[:, :, 1], canvas[:, :, 2]
    r_shifted = np.roll(r, dx, axis=1)
    b_shifted = np.roll(b, -dx, axis=1)
    return np.stack([r_shifted, g, b_shifted], axis=2)


# ============================================================
# パターン1: letterbox — 上下黒バー + 中央16:9 + テロップ
# ============================================================
def _render_letterbox_telop(text, canvas_w, cfg):
    """上部黒バーに配置する大テロップ"""
    key = ("lb_telop", text)
    if key in _subtitle_cache:
        return _subtitle_cache[key]
    fs = cfg.get('font_size', 72)
    ow = cfg.get('outline_width', 8)
    h = cfg.get('height', 450)
    pad_top = cfg.get('pad_top', 40)
    ls = cfg.get('line_spacing', fs + 20)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc", fs)
    except Exception:
        font = ImageFont.load_default()
    panel = Image.new('RGBA', (canvas_w, h), (0, 0, 0, 255))  # 黒背景（不透明）
    draw = ImageDraw.Draw(panel)
    parts = _parse_colored_text(text)
    plain = ''.join(p[0] for p in parts)
    lines = _wrap_text(plain, font, canvas_w - 80, draw)
    # テロップを黒バー内で垂直中央に配置
    total_h = len(lines[:4]) * ls
    y_start = max(pad_top, (h - total_h) // 2)
    _draw_colored_lines(draw, lines[:4], parts, font, canvas_w, y_start, ls, ow,
                        base_font_size=fs)
    result = np.array(panel, dtype=np.uint8)
    _subtitle_cache[key] = result
    return result


def _render_letterbox_bottom(text, canvas_w, cfg):
    """下部黒バーのテキスト（補足説明、小さめ）"""
    key = ("lb_bottom", text)
    if key in _subtitle_cache:
        return _subtitle_cache[key]
    fs = cfg.get('font_size', 40)
    ow = cfg.get('outline_width', 5)
    h = cfg.get('height', 300)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", fs)
    except Exception:
        font = ImageFont.load_default()
    panel = Image.new('RGBA', (canvas_w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(panel)
    parts = _parse_colored_text(text)
    plain = ''.join(p[0] for p in parts)
    lines = _wrap_text(plain, font, canvas_w - 80, draw)
    _draw_colored_lines(draw, lines[:3], parts, font, canvas_w, 40, fs + 16, ow,
                        base_font_size=fs)
    result = np.array(panel, dtype=np.uint8)
    _subtitle_cache[key] = result
    return result


# ============================================================
# パターン3: combined — 上部黒バー（テーマタイトル）
# ============================================================
def _render_combined_top_bar(text, canvas_w, cfg):
    """上部黒バーにテーマタイトルを表示"""
    key = ("combined_top", text)
    if key in _subtitle_cache:
        return _subtitle_cache[key]
    fs = cfg.get('font_size', 52)
    ow = cfg.get('outline_width', 0)
    h = cfg.get('height', 200)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc", fs)
    except Exception:
        font = ImageFont.load_default()
    panel = Image.new('RGBA', (canvas_w, h), (0, 0, 0, 255))
    draw = ImageDraw.Draw(panel)
    parts = _parse_colored_text(text)
    plain = ''.join(p[0] for p in parts)
    lines = _wrap_text(plain, font, canvas_w - 80, draw)
    total_h = len(lines[:2]) * (fs + 16)
    y_start = (h - total_h) // 2
    _draw_colored_lines(draw, lines[:2], parts, font, canvas_w, y_start, fs + 16, ow,
                        base_font_size=fs)
    result = np.array(panel, dtype=np.uint8)
    _subtitle_cache[key] = result
    return result


# ============================================================
# パターン2: native_vertical — 中央字幕（背景なし、白+黒縁のみ）
# ============================================================
def _render_center_subtitle(text, canvas_w, cfg):
    """画面中央付近のクリーンな字幕。背景なし。"""
    key = ("center_sub", text)
    if key in _subtitle_cache:
        return _subtitle_cache[key]
    fs = cfg.get('font_size', 58)
    ow = cfg.get('outline_width', 8)
    h = cfg.get('height', 200)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc", fs)
    except Exception:
        font = ImageFont.load_default()
    # 完全透明キャンバス（背景なし）
    panel = Image.new('RGBA', (canvas_w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(panel)
    parts = _parse_colored_text(text)
    plain = ''.join(p[0] for p in parts)
    lines = _wrap_text(plain, font, canvas_w - 80, draw)
    max_lines = cfg.get('max_lines', 2)
    if len(lines) > max_lines:
        print(f"  ⚠️ 字幕が{len(lines)}行（max_lines={max_lines}超過）: \"{plain[:30]}...\" → 切り捨て発生。split_subtitleのmax_charsを下げてください")
    total_h = len(lines[:max_lines]) * (fs + 16)
    y_start = (h - total_h) // 2
    _draw_colored_lines(draw, lines[:max_lines], parts, font, canvas_w, y_start, fs + 16, ow,
                        base_font_size=fs)
    result = np.array(panel, dtype=np.uint8)
    _subtitle_cache[key] = result
    return result


# ============================================================
# フレームレンダリング
# ============================================================
def _get_panel(event, ip_w, ip_h, current_time):
    """画像/動画パネルを取得（Ken Burns対応・動画アセット対応）"""
    asset = event['params']['asset']

    # 動画アセットの場合: フレームを直接取得（Ken Burns不要）
    if _is_video_asset(asset):
        elapsed = current_time - event['time_start']
        dur = event['time_end'] - event['time_start']
        return get_video_frame(asset, ip_w, ip_h, elapsed, dur)

    use_kb = event['params'].get('ken_burns', False)
    if use_kb:
        dur = event['time_end'] - event['time_start']
        prog = min(1.0, max(0.0, (current_time - event['time_start']) / dur)) if dur > 0 else 0
        kb_intensity = event['params'].get('kb_intensity', 1.0)
        # kb_direction: 明示指定があればそれを使用、なければ自動ローテーション
        kb_dir = event['params'].get('kb_direction')
        if kb_dir and kb_dir in _KB_DIRECTIONS:
            kb_index = _KB_DIRECTIONS.index(kb_dir)
        else:
            kb_index = int(event['time_start'] * 10) % 4
        kb_focus = event['params'].get('kb_focus')
        return apply_ken_burns(asset, ip_w, ip_h, prog, kb_index, kb_intensity, focus=kb_focus)
    return get_static_image(asset, ip_w, ip_h)


def render_frame(plan, frame_num, fps, width, height):
    current_time = frame_num / fps
    layout = plan['layout']
    lt = layout.get('type', 'letterbox')

    # アクティブイベント収集
    active = {}
    for ev in plan['timeline']:
        if ev['time_start'] <= current_time < ev['time_end']:
            active[ev['layer']] = ev

    if lt == 'letterbox':
        # === パターン1: 上下黒バー + 中央16:9コンテンツ ===
        top_cfg = layout.get('top_bar', {})
        bot_cfg = layout.get('bottom_bar', {})
        content_cfg = layout.get('content', {})

        top_h = top_cfg.get('height', 450)
        bot_h = bot_cfg.get('height', 300)
        content_h = height - top_h - bot_h  # 残り = 1170px (≒16:9の1080x608をフィット)
        content_y = top_h

        # 黒背景
        canvas = np.zeros((height, width, 3), dtype=np.uint8)

        # 中央コンテンツ
        if 'info_panel' in active:
            panel = _get_panel(active['info_panel'], width, content_h, current_time)
            canvas[content_y:content_y + content_h, :] = panel

        # 上部テロップ
        if 'subtitle' in active:
            text = active['subtitle']['params'].get('text', '')
            telop = _render_letterbox_telop(text, width, top_cfg)
            alpha_blend(canvas, telop, 0, 0)

        # 下部テキスト
        if 'bottom_text' in active:
            text = active['bottom_text']['params'].get('text', '')
            bot = _render_letterbox_bottom(text, width, bot_cfg)
            alpha_blend(canvas, bot, 0, height - bot_h)

        return canvas

    elif lt == 'native_vertical':
        # === パターン2: 全画面9:16画像 + 中央字幕 ===
        ip = layout.get('info_panel', {'x': 0, 'y': 0, 'width': width, 'height': height})
        sub_cfg = layout.get('subtitle', {})

        canvas = np.full((height, width, 3), (20, 20, 30), dtype=np.uint8)

        if 'info_panel' in active:
            panel = _get_panel(active['info_panel'], ip['width'], ip['height'], current_time)
            canvas[ip['y']:ip['y'] + ip['height'], ip['x']:ip['x'] + ip['width']] = panel

        if 'subtitle' in active:
            text = active['subtitle']['params'].get('text', '')
            sub = _render_center_subtitle(text, width, sub_cfg)
            if sub is not None:
                sub_y = sub_cfg.get('y', int(height * 0.53))
                alpha_blend(canvas, sub, 0, sub_y)

        return canvas

    elif lt == 'combined':
        # === パターン3: 上部黒バー(テーマ) + 9:16コンテンツ + 中央字幕 ===
        top_cfg = layout.get('top_bar', {})
        content_cfg = layout.get('content', {})
        sub_cfg = layout.get('subtitle', {})

        top_h = top_cfg.get('height', 200)
        content_y = content_cfg.get('y', top_h)
        content_w = content_cfg.get('width', width)
        content_h = content_cfg.get('height', height - top_h)
        content_scale = content_cfg.get('scale', 1.0)

        # スケール適用: 描画領域の計算
        if content_scale < 1.0:
            eff_w = int(content_w * content_scale)
            eff_h = int(content_h * content_scale)
            eff_x = (content_w - eff_w) // 2
            eff_y = content_y + (content_h - eff_h) // 2
        else:
            eff_w, eff_h = content_w, content_h
            eff_x, eff_y = 0, content_y

        # 黒背景
        canvas = np.zeros((height, width, 3), dtype=np.uint8)

        # コンテンツ（Ken Burns対応、スケール反映）
        if 'info_panel' in active:
            panel = _get_panel(active['info_panel'], eff_w, eff_h, current_time)
            canvas[eff_y:eff_y + eff_h, eff_x:eff_x + eff_w] = panel

        # 上部黒バー（テーマタイトル）
        theme = plan.get('theme_title', '')
        if theme:
            top_bar = _render_combined_top_bar(theme, width, top_cfg)
            alpha_blend(canvas, top_bar, 0, 0)

        # 集中線（スケール反映）
        show_concentration = layout.get('effects', {}).get('concentration_lines', False)
        if not show_concentration and 'info_panel' in active:
            show_concentration = active['info_panel']['params'].get('effects', {}).get('concentration_lines', False)
        if show_concentration:
            seed = int(current_time * 4) % 20
            cl = _render_concentration_lines(eff_w, eff_h, seed=seed)
            alpha_blend(canvas, cl, eff_x, eff_y)

        # シーンエフェクト適用
        if 'info_panel' in active:
            scene_fx = active['info_panel']['params'].get('effects', {})
            scene_elapsed = current_time - active['info_panel']['time_start']

            if scene_fx.get('flash'):
                canvas = _apply_flash(canvas, scene_elapsed)
            if scene_fx.get('bounce_in'):
                canvas = _apply_bounce_in(canvas, eff_y, eff_h, scene_elapsed)
            if scene_fx.get('shake'):
                shake_int = scene_fx.get('shake_intensity', 6)
                canvas = _apply_camera_shake(canvas, scene_elapsed, intensity=shake_int)
            if scene_fx.get('rgb_shift'):
                canvas = _apply_rgb_shift(canvas, scene_elapsed, intensity=scene_fx.get('rgb_intensity', 4))

        # 中央字幕（ポップインアニメーション付き）
        if 'subtitle' in active:
            ev = active['subtitle']
            text = ev['params'].get('text', '')
            sub = _render_center_subtitle(text, width, sub_cfg)
            if sub is not None:
                sub_y = sub_cfg.get('y', int(height * 0.56))
                elapsed = current_time - ev['time_start']
                # ポップイン: 最初の0.1秒でスケールアップ
                pop_dur = 0.1
                if elapsed < pop_dur:
                    t = elapsed / pop_dur
                    scale = 0.85 + 0.15 * (1.0 - (1.0 - t) ** 2)
                    sh, sw = sub.shape[:2]
                    ns_w, ns_h = int(sw * scale), int(sh * scale)
                    sub_scaled = cv2.resize(sub, (ns_w, ns_h), interpolation=cv2.INTER_LINEAR)
                    pad_x = (sw - ns_w) // 2
                    pad_y = (sh - ns_h) // 2
                    padded = np.zeros_like(sub)
                    padded[pad_y:pad_y+ns_h, pad_x:pad_x+ns_w] = sub_scaled
                    sub = padded
                # テキストシェイク（字幕にshake指定がある場合）
                sub_fx = ev['params'].get('effects', {})
                if sub_fx.get('shake'):
                    sub = _apply_subtitle_shake(sub, elapsed, intensity=sub_fx.get('shake_intensity', 4))
                alpha_blend(canvas, sub, 0, sub_y)

        return canvas

    # フォールバック
    return np.zeros((height, width, 3), dtype=np.uint8)


# ============================================================
# SE + BGM 音声ミキシング
# ============================================================
SE_VOLUME = 0.3


def mix_audio(plan, output_dir, duration):
    """音声 + SE + BGM をミックスして出力"""
    # WAV優先（AAC truncation回避）、後方互換でAACも受け付ける
    voice_path = output_dir / "mixed_audio.wav"
    if not voice_path.exists():
        voice_path = output_dir / "mixed_audio.aac"
    if not voice_path.exists():
        manifest_path = output_dir / "audio" / "audio_manifest.json"
        if manifest_path.exists():
            voice_path = _premix_voice(manifest_path, output_dir, duration)
        if not voice_path or not voice_path.exists():
            return None

    # Collect SE events
    se_events = [e for e in plan.get("timeline", [])
                 if e.get("layer") == "se" and e["params"].get("file")]

    # BGM config
    bgm_cfg = plan.get("bgm", {})
    bgm_file_rel = bgm_cfg.get("file")
    bgm_vol = bgm_cfg.get("volume", 0.04)
    bgm_loop = bgm_cfg.get("loop", True)
    bgm_path = PROJECT_ROOT / bgm_file_rel if bgm_file_rel else None

    has_se = bool(se_events)
    has_bgm = bgm_path and bgm_path.exists()

    if not has_se and not has_bgm:
        return voice_path

    parts_info = []
    if has_se:
        parts_info.append(f"{len(se_events)} SE")
    if has_bgm:
        parts_info.append(f"BGM({bgm_file_rel})")
    print(f"  Mixing: {', '.join(parts_info)}")

    # Build FFmpeg inputs and filter
    inputs = ['-i', str(voice_path)]  # input 0 = voice
    filter_parts = []
    mix_labels = ['[0]']  # voice is always first

    # SE inputs
    se_idx = 0
    for i, ev in enumerate(se_events):
        se_file = PROJECT_ROOT / ev["params"]["file"]
        if not se_file.exists():
            print(f"  WARNING: SE not found: {se_file}")
            continue
        idx = len(inputs) // 2
        inputs.extend(['-i', str(se_file)])
        delay_ms = int(ev["time_start"] * 1000)
        label = f'se{se_idx}'
        filter_parts.append(
            f"[{idx}]volume={SE_VOLUME},aresample=48000,adelay={delay_ms}|{delay_ms}[{label}]"
        )
        mix_labels.append(f'[{label}]')
        se_idx += 1

    # BGM input (with loop support via -stream_loop)
    if has_bgm:
        bgm_idx = len(inputs) // 2
        if bgm_loop:
            # Insert -stream_loop before -i for this input
            inputs.extend(['-stream_loop', '-1', '-i', str(bgm_path)])
        else:
            inputs.extend(['-i', str(bgm_path)])
        label = 'bgm'
        filter_parts.append(
            f"[{bgm_idx}]loudnorm=I=-16:TP=-1:LRA=11,volume={bgm_vol},aresample=48000,afade=t=in:d=1.0,afade=t=out:st={duration - 2.0}:d=2.0[{label}]"
        )
        mix_labels.append(f'[{label}]')

    if len(mix_labels) <= 1:
        return voice_path

    # Amix all tracks
    all_labels = ''.join(mix_labels)
    n = len(mix_labels)
    filter_complex = ';'.join(filter_parts)
    filter_complex += f';{all_labels}amix=inputs={n}:duration=first:dropout_transition=0:normalize=0[out]'

    output_path = output_dir / "mixed_audio_final.aac"
    cmd = ['ffmpeg', '-y'] + inputs + [
        '-filter_complex', filter_complex,
        '-map', '[out]',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000',
        '-t', str(duration),
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Audio mix failed: {result.stderr[-300:]}")
        return voice_path
    print(f"  Audio mix done: {output_path}")
    return output_path


def _premix_voice(manifest_path, output_dir, duration):
    """audio_manifest.jsonから音声をpremix"""
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    segments = manifest.get("segments", [])
    if not segments:
        return None

    audio_dir = manifest_path.parent
    SEGMENT_GAP = 0.3  # scenes.jsonのセグメント間ギャップと一致させる

    inputs = []
    filter_parts = []
    concat_labels = []
    for i, seg in enumerate(segments):
        wav = audio_dir / seg["file"]
        if not wav.exists():
            continue
        idx = len(inputs) // 2
        inputs.extend(['-i', str(wav)])
        seg_label = f's{idx}'
        filter_parts.append(f'[{idx}]aresample=48000[{seg_label}]')
        concat_labels.append(f'[{seg_label}]')
        if i < len(segments) - 1:
            gap_label = f'g{idx}'
            filter_parts.append(f'aevalsrc=0:d={SEGMENT_GAP}:s=48000[{gap_label}]')
            concat_labels.append(f'[{gap_label}]')

    if not concat_labels:
        return None

    all_labels = ''.join(concat_labels)
    n = len(concat_labels)
    fc = ';'.join(filter_parts) + f';{all_labels}concat=n={n}:v=0:a=1[out]'
    # WAV出力（AAC encoder truncation回避 — 末尾数秒が消える問題の対策）
    output_path = output_dir / "mixed_audio.wav"
    cmd = ['ffmpeg', '-y'] + inputs + [
        '-filter_complex', fc, '-map', '[out]',
        '-c:a', 'pcm_s16le', '-ar', '48000',
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  Voice premix failed: {result.stderr[-300:]}")
        return None
    return output_path


# ============================================================
# Preflight Validation（レンダリング前バリデーション）
# ============================================================
def preflight_check(plan, plan_path):
    """render_plan.jsonの品質チェック。エラーがあればレンダリングを停止する。
    根拠: case_studies/2026-03-08_shorts-rendering-lessons.md (問題1-7)
    """
    errors = []
    warnings = []
    layout = plan.get('layout', {})
    sub_cfg = layout.get('subtitle', {})
    font_size = sub_cfg.get('font_size', 84)
    canvas_w = plan.get('canvas', {}).get('width', 1080)
    max_lines = sub_cfg.get('max_lines', 2)

    # 実際のフォントで行数チェック（文字数推定ではなく正確な折り返し）
    try:
        _pf_font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W9.ttc", font_size)
    except Exception:
        _pf_font = ImageFont.load_default()
    _pf_img = Image.new('RGBA', (canvas_w, 100), (0, 0, 0, 0))
    _pf_draw = ImageDraw.Draw(_pf_img)

    for ev in plan.get('timeline', []):
        if ev.get('layer') != 'subtitle':
            continue
        text = ev.get('params', {}).get('text', '')
        # チェック1: 手動改行 \n の検出（問題3）
        if '\n' in text:
            errors.append(
                f"  字幕に手動改行あり (t={ev['time_start']:.1f}s): "
                f"'{text[:30]}...' → \\n を除去してください"
            )
        # チェック2: 実際のフォントレンダリングで行数超過を検出
        plain = ''.join(p[0] for p in _parse_colored_text(text))
        actual_lines = _wrap_text(plain, _pf_font, canvas_w - 80, _pf_draw)
        if len(actual_lines) > max_lines:
            errors.append(
                f"  字幕{len(actual_lines)}行超過 (t={ev['time_start']:.1f}s, {len(plain)}文字): "
                f"'{plain[:30]}...' → split_subtitleのmax_charsを下げるか分割してください"
            )

    # チェック3: アセットパスの存在確認
    for ev in plan.get('timeline', []):
        if ev.get('layer') != 'info_panel':
            continue
        asset = ev.get('params', {}).get('asset', '')
        if asset and not (PROJECT_ROOT / asset).exists():
            errors.append(f"  アセット不在: {asset}")

    # チェック3.5: scene_review.json全承認ゲート（モードA必須）
    # generate_render_plan.py を経由せず手動でrender_plan.jsonを書いた場合でもブロック
    plan_dir = Path(plan_path).parent
    review_path = plan_dir / "scene_review.json"
    skip_review = os.environ.get("SKIP_REVIEW") == "1"  # モードB用の環境変数バイパス
    if skip_review:
        pass  # モードB: スキップ
    elif not review_path.exists():
        errors.append(
            f"  scene_review.json が見つかりません → Phase 3 Tinderレビュー未実施\n"
            f"    → python3 scripts/panel_mapping_reviewer.py --shorts {plan_dir}"
        )
    else:
        with open(review_path, 'r', encoding='utf-8') as rf:
            reviews = json.load(rf)
        # render_plan内の全シーンアセットに対応するレビューを確認
        scene_ids = set()
        for ev in plan.get('timeline', []):
            if ev.get('layer') == 'info_panel':
                asset = ev.get('params', {}).get('asset', '')
                # アセットパスからscene_idを抽出（例: scene_01）
                m = re.search(r'(scene_\d+)', asset)
                if m:
                    scene_ids.add(m.group(1))
        unapproved = []
        for sid in sorted(scene_ids):
            entry = reviews.get(sid, {})
            if not (entry.get("status") == "ok" or entry.get("approved", False)):
                unapproved.append(sid)
        if unapproved:
            errors.append(
                f"  未承認シーン: {', '.join(unapproved)}\n"
                f"    → Phase 3 Tinderレビューで全シーンを承認してください\n"
                f"    → python3 scripts/panel_mapping_reviewer.py --shorts {plan_dir}"
            )

    # チェック4+5: mixed_audio.aacの尺チェック（duration整合性 + 50秒未満ゲート）
    mixed_audio = plan_dir / "mixed_audio.aac"
    duration_sec = plan.get("duration_sec", 0)
    if mixed_audio.exists():
        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'csv=p=0', str(mixed_audio)],
            capture_output=True, text=True
        )
        if probe.returncode == 0 and probe.stdout.strip():
            audio_dur = float(probe.stdout.strip())
            # チェック4: duration_secとの整合性
            if duration_sec > 0:
                if audio_dur < duration_sec * 0.8:
                    errors.append(
                        f"  mixed_audio.aac尺不足: {audio_dur:.1f}s (期待値: {duration_sec:.1f}s) "
                        f"→ pipeline_shorts.pyで再生成してください"
                    )
                elif audio_dur < duration_sec * 0.95:
                    warnings.append(
                        f"  mixed_audio.aac尺がやや短い: {audio_dur:.1f}s (期待値: {duration_sec:.1f}s)"
                    )
            # チェック5: 50秒未満ゲート（モードA/B共通）
            if audio_dur < 50.0:
                errors.append(
                    f"  音声が{audio_dur:.1f}秒 → 50秒未満ゲート発動\n"
                    f"    → 台本を加筆修正して再生成してください"
                )
            # チェック5.5: 60秒超過ゲート（YouTube Shorts上限）
            if audio_dur > 60.0:
                errors.append(
                    f"  音声尺が60秒を超えています（{audio_dur:.1f}s）。Shorts上限は60秒です"
                )

    # info_panelsリストを事前構築（チェック6-8で共有）
    info_panels = [ev for ev in plan.get('timeline', []) if ev.get('layer') == 'info_panel']
    info_panels_sorted = sorted(info_panels, key=lambda e: e.get('time_start', 0))

    # チェック6: 画像10枚未満ゲート（モードA/B共通）
    if len(info_panels) < 10:
        errors.append(
            f"  画像が{len(info_panels)}枚 → 10枚未満ゲート発動\n"
            f"    → シーン分割を見直して追加してください"
        )

    # チェック7: scene_01のflash/shake禁止 + time_start=0.0
    if info_panels_sorted:
        first_panel = info_panels_sorted[0]
        fp_fx = first_panel.get('params', {}).get('effects', {})
        if fp_fx.get('flash'):
            errors.append(
                f"  scene_01にflash効果 → 開始直後の白フラッシュ\n"
                f"    → render_plan.jsonから削除してください"
            )
        if fp_fx.get('shake'):
            warnings.append(
                f"  scene_01にshake効果 → 開始直後の映像揺れ\n"
                f"    → render_plan.jsonから削除を推奨"
            )
        if first_panel.get('time_start', 0) > 0:
            errors.append(
                f"  scene_01のtime_start={first_panel['time_start']}s → 冒頭ブラックアウト\n"
                f"    → time_start=0.0に修正してください"
            )

    # チェック8: エンディング固定画像の再利用チェック
    # ※オープニングは毎回テーマに合わせて新規生成（バリエーション確保のため）
    fixed_ending = "assets/image_library/fixed/ending_amy.png"
    if info_panels_sorted:
        last_asset = info_panels_sorted[-1].get('params', {}).get('asset', '')
        if (PROJECT_ROOT / fixed_ending).exists() and fixed_ending not in last_asset:
            warnings.append(
                f"  エンディング画像が固定画像ではありません: {last_asset}\n"
                f"    → {fixed_ending} の使用を推奨"
            )

    # 結果出力
    if warnings:
        print(f"⚠️  Preflight warnings ({len(warnings)}):")
        for w in warnings:
            print(w)
    if errors:
        print(f"❌ Preflight FAILED ({len(errors)} errors):")
        for e in errors:
            print(e)
        print("\nレンダリングを中止しました。上記の問題を修正してから再実行してください。")
        return False
    print("✅ Preflight check passed")
    return True


# ============================================================
# FFmpeg出力
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Shorts縦動画レンダラー")
    parser.add_argument("plan", help="render_plan JSON")
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--output", "-o", type=str, default=None)
    args = parser.parse_args()

    plan_path = Path(args.plan)
    output_dir = plan_path.parent
    output_file = Path(args.output) if args.output else output_dir / "shorts_test.mp4"

    with open(plan_path, 'r', encoding='utf-8') as f:
        plan = json.load(f)

    # Preflight validation — 問題があればここで停止
    if not preflight_check(plan, plan_path):
        return False

    dur = plan['duration_sec']
    fps = plan['canvas']['fps']
    w, h = plan['canvas']['width'], plan['canvas']['height']
    total = int(dur * fps)

    print(f"Shorts: {w}x{h} @ {fps}fps, {dur:.1f}s | {plan['layout'].get('type')}")

    # Audio mixing step (voice + SE + BGM)
    audio_path = None
    if not args.silent:
        audio_path = mix_audio(plan, output_dir, dur)

    chk = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True)
    hw = 'h264_videotoolbox' in chk.stdout
    has_audio = audio_path and audio_path.exists()

    cmd = ['ffmpeg', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
           '-s', f'{w}x{h}', '-r', str(fps), '-i', 'pipe:0']
    if has_audio:
        cmd.extend(['-i', str(audio_path)])
    else:
        cmd.extend(['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo'])
    cmd.extend(['-c:v', 'h264_videotoolbox', '-q:v', '65'] if hw else
               ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20'])
    cmd.extend(['-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
                '-t', str(dur), '-movflags', '+faststart', str(output_file)])

    print(f"  Encoder: {'HW' if hw else 'SW'} | Output: {output_file}")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    t0 = time.time()

    for fn in range(total):
        proc.stdin.write(render_frame(plan, fn, fps, w, h).tobytes())
        if fn % (fps * 5) == 0:
            print(f"  {fn / total * 100:5.1f}%")

    proc.stdin.close()
    stderr = proc.stderr.read().decode()
    proc.wait()

    if proc.returncode != 0:
        print(f"FFmpeg error: {stderr[-500:]}")
        return False
    file_mb = os.path.getsize(output_file) / 1024 / 1024
    # 事後チェック: 10秒あたり1MB未満は異常（問題7対策）
    mb_per_10s = file_mb / max(dur / 10, 0.1)
    if mb_per_10s < 1.0:
        print(f"⚠️  ファイルサイズ異常: {file_mb:.1f}MB ({mb_per_10s:.1f}MB/10s) — ffmpegコマンドを確認してください")
    print(f"Done! {time.time() - t0:.1f}s | {file_mb:.1f}MB")
    return True


if __name__ == "__main__":
    main()
