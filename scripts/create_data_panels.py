#!/usr/bin/env python3
"""
データパネル画像生成 v7.1 - デザインルール強化版
1344x756 JPG（新レイアウト対応）

改善点 (v7.1):
- 文字数制限の厳格化（各要素ごとに上限設定）
- テキスト幅測定による自動フォントサイズ縮小
- 空白バランス最適化（下部余白ゼロ設計）
- 全テキスト中央揃え（anchor="mm"）統一
- 見切れ防止（描画前にサイズ検証）

使い方:
    cat panels.json | python3 create_data_panels_v7.py

入力JSON形式:
[
  {
    "filename": "panel_name.jpg",
    "title": "パネルタイトル",
    "layout": "timeline",  // timeline, summary, title_card, detail_list
    "items": [
      {"year": "1996", "label": "社民党に改称", "description": "村山政権～..."},
      ...
    ]
  },
  ...
]
"""

import json
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

PROJECT_ROOT = Path(__file__).parent.parent
PANELS_DIR = PROJECT_ROOT / "assets/panels"
PANELS_DIR.mkdir(parents=True, exist_ok=True)

# --- パネルサイズ ---
PW, PH = 1344, 756

# --- フォント設定 ---
FONT_W3 = "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc"
FONT_W6 = "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc"
FONT_W8 = "/System/Library/Fonts/ヒラギノ角ゴシック W8.ttc"

def get_font(weight="W6", size=40):
    fonts = {"W3": FONT_W3, "W6": FONT_W6, "W8": FONT_W8}
    return ImageFont.truetype(fonts.get(weight, FONT_W6), size)

# --- カラーパレット ---
ACCENT_COLORS = ['#1A73E8', '#FF9800', '#E91E63', '#4CAF50', '#9C27B0']
TIMELINE_COLORS = ['#1A73E8', '#FFC107', '#4CAF50', '#FF9800', '#F44336', '#9C27B0']


# ============================================================
# テキストヘルパー関数
# ============================================================

# --- 文字数上限（レイアウト×要素ごと） ---
TEXT_LIMITS = {
    "timeline": {"title": 16, "year": 6, "label": 10, "description": 36, "footer_line": 30, "footer_highlight": 25},
    "summary": {"title": 12, "item_title": 18, "item_text": 22, "cta": 15},
    "title_card": {"badge": 8, "main_text": 10, "subtitle_line": 18, "footer_line": 22},
    "detail_list": {"title": 18, "badge": 4, "text": 28, "rating": 5},
}


def truncate_text(text: str, max_chars: int) -> str:
    """文字数制限。超過時は末尾を '...' で切り詰める。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + "..."


def fit_text_font(draw: ImageDraw.Draw, text: str, weight: str, target_size: int,
                  max_width: int, min_size: int = 16) -> ImageFont.FreeTypeFont:
    """テキスト幅がmax_width以内に収まるようフォントサイズを縮小。
    anchor="mm" (中央揃え) で描画する前提。"""
    size = target_size
    while size >= min_size:
        font = get_font(weight, size)
        bbox = draw.textbbox((0, 0), text, font=font, anchor="mm")
        text_w = bbox[2] - bbox[0]
        if text_w <= max_width:
            return font
        size -= 2
    return get_font(weight, min_size)


# ============================================================
# レイアウト1: timeline（タイムライン型）
# ============================================================
def create_timeline_panel(title, items, footer_text=None, footer_highlight=None):
    """
    タイムライン型パネル
    - 白/薄グレー背景、紫ヘッダー
    - 白カード（最大6個、2行）、カラフルアクセントライン
    - タイムライン横線と点
    - 下部: 説明文 + 赤い強調文
    - 全テキスト中央揃え、下部余白ゼロ
    """
    limits = TEXT_LIMITS["timeline"]
    title = truncate_text(title, limits["title"])

    img = Image.new('RGB', (PW, PH), '#F5F5F5')
    draw = ImageDraw.Draw(img)

    # ヘッダー（紫）
    draw.rectangle([0, 0, PW, 50], fill='#7B1FA2')
    title_font = fit_text_font(draw, title, "W8", 36, PW - 220)
    draw.text((30, 25), title, fill='#FFFFFF', font=title_font, anchor="lm")

    # TIMELINEバッジ右上
    badge_w = 150
    draw.rounded_rectangle([PW-badge_w-20, 10, PW-20, 40], radius=15, fill='#FFFFFF')
    draw.text((PW-badge_w//2-20, 25), "TIMELINE", fill='#7B1FA2', font=get_font("W8", 20), anchor="mm")

    # アイテム数（最大6個、2行配置）
    num_items = min(len(items), 6)
    row1_count = (num_items + 1) // 2
    row2_count = num_items - row1_count

    card_w, card_h, gap_x = 420, 170, 80

    # 行1のX開始位置（中央揃え）
    row1_total_w = row1_count * card_w + (row1_count - 1) * gap_x
    row1_start_x = (PW - row1_total_w) // 2

    # 行2のX開始位置
    row2_start_x = 0
    if row2_count > 0:
        row2_total_w = row2_count * card_w + (row2_count - 1) * gap_x
        row2_start_x = (PW - row2_total_w) // 2

    # Y位置（余白35px統一、下部余白最小化）
    row1_card_y = 65
    row1_timeline_y = 270
    row2_card_y = 305
    row2_timeline_y = 510

    row1_points = []
    row2_points = []

    for i, item in enumerate(items[:num_items]):
        if i < row1_count:
            x = row1_start_x + i * (card_w + gap_x)
            y = row1_card_y
            color = TIMELINE_COLORS[i % len(TIMELINE_COLORS)]
            row1_points.append((x + card_w//2, row1_timeline_y, color))
        else:
            x = row2_start_x + (i - row1_count) * (card_w + gap_x)
            y = row2_card_y
            color = TIMELINE_COLORS[i % len(TIMELINE_COLORS)]
            row2_points.append((x + card_w//2, row2_timeline_y, color))

        # カードシャドウ
        shadow = Image.new('RGBA', (card_w+10, card_h+10), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle([5, 5, card_w+5, card_h+5], radius=8, fill=(0, 0, 0, 40))
        shadow = shadow.filter(ImageFilter.GaussianBlur(5))
        img.paste(shadow, (x-2, y-2), shadow)

        draw.rounded_rectangle([x, y, x+card_w, y+card_h], radius=8, fill='#FFFFFF')
        draw.rounded_rectangle([x, y, x+card_w, y+5], radius=8, fill=color)
        draw.rectangle([x, y+2, x+card_w, y+5], fill=color)

        # 年号（中央揃え、文字数制限）
        year = truncate_text(item.get("year", ""), limits["year"])
        draw.text((x+card_w//2, y+42), year, fill=color, font=get_font("W8", 56), anchor="mm")

        # ラベル（中央揃え、自動縮小）
        label = truncate_text(item.get("label", ""), limits["label"])
        label_font = fit_text_font(draw, label, "W8", 32, card_w - 20)
        draw.text((x+card_w//2, y+90), label, fill='#1A1A1A', font=label_font, anchor="mm")

        # 説明（中央揃え、2行、文字数制限）
        description = truncate_text(item.get("description", ""), limits["description"])
        if description:
            max_chars_per_line = 18
            if len(description) > max_chars_per_line:
                line1 = description[:max_chars_per_line]
                line2 = truncate_text(description[max_chars_per_line:], max_chars_per_line)
                draw.text((x+card_w//2, y+125), line1, fill='#666666', font=get_font("W3", 20), anchor="mm")
                draw.text((x+card_w//2, y+148), line2, fill='#666666', font=get_font("W3", 20), anchor="mm")
            else:
                draw.text((x+card_w//2, y+135), description, fill='#666666', font=get_font("W3", 20), anchor="mm")

    # タイムライン横線
    if len(row1_points) > 1:
        draw.line([(row1_points[0][0], row1_timeline_y), (row1_points[-1][0], row1_timeline_y)], fill='#CCCCCC', width=3)
    if len(row2_points) > 1:
        draw.line([(row2_points[0][0], row2_timeline_y), (row2_points[-1][0], row2_timeline_y)], fill='#CCCCCC', width=3)

    for px, py, color in row1_points + row2_points:
        draw.ellipse([px-8, py-8, px+8, py+8], fill=color, outline='#FFFFFF', width=2)

    # 下部補足説明エリア
    if footer_text or footer_highlight:
        footer_y = 545

        if footer_text:
            lines = footer_text.split('\n')
            for i, line in enumerate(lines[:3]):
                line = truncate_text(line, limits["footer_line"])
                draw.text((PW//2, footer_y+i*40), line, fill='#666666', font=get_font("W3", 28), anchor="mm")

        if footer_highlight:
            highlight_y = footer_y + 125 if footer_text else footer_y
            hl_text = truncate_text(footer_highlight, limits["footer_highlight"])
            hl_font = fit_text_font(draw, hl_text, "W8", 64, PW - 100)
            draw.text((PW//2, highlight_y), hl_text, fill='#E53935', font=hl_font, anchor="mm")

    return img


# ============================================================
# レイアウト2: summary（まとめ・番号リスト型）
# ============================================================
def create_summary_panel(title, items, cta_text=None):
    """
    まとめ型パネル
    - 黒背景、赤ヘッダー
    - 番号バッジ + カラフル枠カード（最大4個）
    - 動的配置: アイテム数に応じて縦方向を自動調整
    - CTA必須（未指定時も空間確保）
    - 全テキスト中央揃え（カード内テキストは左揃え）
    """
    limits = TEXT_LIMITS["summary"]
    title = truncate_text(title, limits["title"])

    img = Image.new('RGB', (PW, PH), '#1A1A1A')
    draw = ImageDraw.Draw(img)

    # ヘッダー（赤）
    draw.rectangle([0, 0, PW, 60], fill='#D32F2F')
    title_font = fit_text_font(draw, title, "W8", 48, PW - 80)
    draw.text((PW//2, 30), title, fill='#FFFFFF', font=title_font, anchor="mm")

    num_items = min(len(items), 4)

    # CTA領域（下部120px確保）
    cta_zone_h = 120 if cta_text else 0
    available_h = PH - 60 - cta_zone_h - 30  # ヘッダー(60) + CTA + 下マージン(30)

    # 動的サイズ計算: アイテム数に応じてカード高さ・間隔を調整
    gap = 20
    total_gap = (num_items - 1) * gap if num_items > 1 else 0
    item_h = min(100, (available_h - total_gap - 40) // max(num_items, 1))
    start_y = 80 + (available_h - num_items * item_h - total_gap) // 2

    for i, item in enumerate(items[:num_items]):
        y = start_y + i * (item_h + gap)
        x = 60
        w = PW - 120

        badge_size = min(80, item_h)
        badge_color = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        draw.rounded_rectangle([x, y, x+badge_size, y+badge_size], radius=12, fill=badge_color)

        icon = item.get("icon", str(i+1))
        draw.text((x+badge_size//2, y+badge_size//2), icon, fill='#FFFFFF', font=get_font("W8", 40), anchor="mm")

        card_x = x + badge_size + 15
        card_w = w - badge_size - 15
        draw.rounded_rectangle([card_x, y, card_x+card_w, y+item_h], radius=12, fill='#1E2A47')
        draw.rounded_rectangle([card_x, y, card_x+card_w, y+item_h], radius=12, outline=badge_color, width=5)

        # テキスト（左揃え、文字数制限、自動縮小）
        text = truncate_text(item.get("text", item.get("label", "")), limits["item_text"])
        text_font = fit_text_font(draw, text, "W6", 36, card_w - 40)
        draw.text((card_x + card_w//2, y + item_h//2), text, fill='#E0E0E0', font=text_font, anchor="mm")

    # CTA（区切り線 + オレンジテキスト）
    if cta_text:
        cta_text = truncate_text(cta_text, limits["cta"])
        cta_y = PH - cta_zone_h
        draw.line([(200, cta_y), (PW-200, cta_y)], fill='#444444', width=2)
        cta_font = fit_text_font(draw, cta_text, "W8", 48, PW - 200)
        draw.text((PW//2, cta_y + 55), cta_text, fill='#FF9800', font=cta_font, anchor="mm")

    return img


# ============================================================
# レイアウト3: title_card（タイトルカード型）
# ============================================================
def create_title_card_panel(title, subtitle, main_text, footer_text=None):
    """
    タイトルカード型パネル（5層構成・空白ゼロ設計）
    - 青ストライプ背景
    - 黒い丸角カード中央配置
    - 5層: バッジ → メインテキスト → サブタイトル → 区切線 → フッター
    - footer_text未指定時もカード全域を使い切る
    - 全テキスト中央揃え
    """
    limits = TEXT_LIMITS["title_card"]
    title = truncate_text(title, limits["badge"])
    main_text = truncate_text(main_text, limits["main_text"])

    img = Image.new('RGB', (PW, PH), '#1565C0')
    draw = ImageDraw.Draw(img)

    # ストライプパターン
    for i in range(-PH, PW + PH, 80):
        draw.line([(i, 0), (i + PH, PH)], fill='#1E88E5', width=30)

    # 中央カード
    card_w, card_h = 1100, 550
    card_x = (PW - card_w) // 2
    card_y = (PH - card_h) // 2
    card_cx = card_x + card_w // 2  # カード水平中央
    text_max_w = card_w - 100  # テキスト描画最大幅（左右50pxマージン）

    # カードシャドウ
    shadow = Image.new('RGBA', (card_w+20, card_h+20), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle([10, 10, card_w+10, card_h+10], radius=25, fill=(0, 0, 0, 80))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    img.paste(shadow, (card_x-5, card_y-5), shadow)

    draw.rounded_rectangle([card_x, card_y, card_x+card_w, card_y+card_h], radius=20, fill='#000000')

    # --- 5層レイアウト計算 ---
    # フッターの有無で層の配置を調整
    has_footer = bool(footer_text)

    if has_footer:
        # 5層: badge(y+70) → main(y+180) → sub(y+280,y+335) → line(y+390) → footer(y+420,y+460)
        badge_y = card_y + 70
        main_y = card_y + 180
        sub_y = card_y + 280
        line_y = card_y + 390
        footer_start_y = card_y + 420
    else:
        # 4層（フッターなし）: 縦方向に均等配分
        badge_y = card_y + 90
        main_y = card_y + 210
        sub_y = card_y + 330

    # 1. バッジ（赤、角括弧、中央揃え）
    badge_text = f"[ {title} ]"
    badge_font = fit_text_font(draw, badge_text, "W8", 56, text_max_w)
    draw.text((card_cx, badge_y), badge_text, fill='#F44336', font=badge_font, anchor="mm")

    # 2. メインテキスト（白、超大、中央揃え）
    main_font = fit_text_font(draw, main_text, "W8", 72, text_max_w)
    draw.text((card_cx, main_y), main_text, fill='#FFFFFF', font=main_font, anchor="mm")

    # 3. サブタイトル（白+赤、中央揃え、最大2行）
    sub_lines = subtitle.split('\n') if subtitle else []
    for i, line in enumerate(sub_lines[:2]):
        line = truncate_text(line, limits["subtitle_line"])
        if i == 0:
            sub_font = fit_text_font(draw, line, "W6", 32, text_max_w)
            draw.text((card_cx, sub_y), line, fill='#FFFFFF', font=sub_font, anchor="mm")
        else:
            sub_font = fit_text_font(draw, line, "W8", 44, text_max_w)
            draw.text((card_cx, sub_y + 55), line, fill='#F44336', font=sub_font, anchor="mm")

    # 4-5. 区切線 + フッター（存在時のみ）
    if has_footer:
        draw.line([(card_x+100, line_y), (card_x+card_w-100, line_y)], fill='#333333', width=2)

        footer_lines = footer_text.split('\n')
        for i, line in enumerate(footer_lines[:2]):
            line = truncate_text(line, limits["footer_line"])
            if i == 0:
                f_font = fit_text_font(draw, line, "W6", 28, text_max_w)
                draw.text((card_cx, footer_start_y), line, fill='#BBBBBB', font=f_font, anchor="mm")
            else:
                f_font = fit_text_font(draw, line, "W6", 36, text_max_w)
                draw.text((card_cx, footer_start_y + 40), line, fill='#FF9800', font=f_font, anchor="mm")

    return img


# ============================================================
# レイアウト4: detail_list（詳細リスト・評価付き）
# ============================================================
def create_detail_list_panel(title, items):
    """
    詳細リスト型パネル
    - 黒背景、青ヘッダー
    - 白カード（最大3個）、動的サイズ調整
    - 番号バッジ + 評価ラベル
    - テキスト見切れ防止（自動縮小）
    """
    limits = TEXT_LIMITS["detail_list"]
    title = truncate_text(title, limits["title"])

    img = Image.new('RGB', (PW, PH), '#000000')
    draw = ImageDraw.Draw(img)

    # ヘッダー（青グラデーション）
    for y in range(70):
        alpha = 1.0 - (y / 70) * 0.3
        r, g, b = 26, 115, 232
        draw.line([(0, y), (PW, y)], fill=(int(r*alpha), int(g*alpha), int(b*alpha)))

    title_font = fit_text_font(draw, title, "W8", 44, PW - 60)
    draw.text((30, 35), title, fill='#FFFFFF', font=title_font, anchor="lm")

    num_items = min(len(items), 3)

    # 動的サイズ: アイテム数に応じてカード高さを調整（空白ゼロ）
    available_h = PH - 70 - 30  # ヘッダー(70) + 下マージン(30)
    gap = 20
    total_gap = (num_items - 1) * gap if num_items > 1 else 0
    item_h = min(200, (available_h - total_gap - 30) // max(num_items, 1))
    start_y = 85 + (available_h - num_items * item_h - total_gap) // 2

    for i, item in enumerate(items[:num_items]):
        y = start_y + i * (item_h + gap)
        x = 60
        w = PW - 120

        # カードシャドウ
        shadow = Image.new('RGBA', (w+10, item_h+10), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle([5, 5, w+5, item_h+5], radius=15, fill=(255, 255, 255, 30))
        shadow = shadow.filter(ImageFilter.GaussianBlur(8))
        img.paste(shadow, (x-2, y-2), shadow)

        draw.rounded_rectangle([x, y, x+w, y+item_h], radius=12, fill='#FFFFFF')

        # 番号バッジ
        badge_size = 70
        badge_color = ACCENT_COLORS[i % len(ACCENT_COLORS)]
        draw.rounded_rectangle([x+20, y+20, x+20+badge_size, y+20+badge_size], radius=10, fill=badge_color)

        badge_text = truncate_text(item.get("badge", f"#{i+1}"), limits["badge"])
        draw.text((x+20+badge_size//2, y+20+badge_size//2), badge_text, fill='#FFFFFF', font=get_font("W8", 28), anchor="mm")

        # テキスト（自動縮小、2行対応）
        text = truncate_text(item.get("text", ""), limits["text"])
        text_x = x + 20 + badge_size + 30
        text_area_w = w - badge_size - 90  # バッジ+マージン分を引く

        max_line_length = 22
        if len(text) > max_line_length:
            line1 = text[:max_line_length]
            line2 = truncate_text(text[max_line_length:], max_line_length)
            f1 = fit_text_font(draw, line1, "W6", 36, text_area_w)
            f2 = fit_text_font(draw, line2, "W6", 36, text_area_w)
            draw.text((text_x, y+40), line1, fill='#1A1A1A', font=f1, anchor="lm")
            draw.text((text_x, y+85), line2, fill='#1A1A1A', font=f2, anchor="lm")
        else:
            tf = fit_text_font(draw, text, "W6", 36, text_area_w)
            draw.text((text_x, y+60), text, fill='#1A1A1A', font=tf, anchor="lm")

        # 評価ラベル
        rating = truncate_text(item.get("rating", ""), limits["rating"])
        if rating:
            rating_colors = {"問題なし": "#4CAF50", "注意": "#FF9800", "NG": "#F44336"}
            rating_color = rating_colors.get(rating, "#4CAF50")
            arrow_y = y + item_h - 50
            draw.text((text_x, arrow_y), "->", fill=rating_color, font=get_font("W8", 36), anchor="lm")
            draw.text((text_x+55, arrow_y), rating, fill=rating_color, font=get_font("W8", 40), anchor="lm")

    return img


# ============================================================
# メイン処理
# ============================================================
# ============================================================
# フルスクリーンパネル（1920x1080）— ナレーション動画用
# ============================================================
FPW, FPH = 1920, 1080  # Fullscreen Panel size

TEXT_LIMITS["section_header"] = {"title": 20, "subtitle": 30}
TEXT_LIMITS["sns_quote"] = {"username": 20, "text": 100, "timestamp": 20}
TEXT_LIMITS["fullscreen_summary"] = {"title": 16, "item_text": 30}


def create_section_header_panel(title, subtitle=None):
    """セクション見出しパネル（1920x1080）。ダークネイビー背景に大きなテキスト。"""
    img = Image.new('RGB', (FPW, FPH), (18, 18, 48))
    draw = ImageDraw.Draw(img)

    title = truncate_text(title, TEXT_LIMITS["section_header"]["title"])

    # アクセントライン（上下）
    draw.rectangle([0, 0, FPW, 8], fill='#D93025')
    draw.rectangle([0, FPH - 8, FPW, FPH], fill='#D93025')

    # 中央の装飾ライン
    cy = FPH // 2
    draw.rectangle([100, cy - 2, FPW - 100, cy + 2], fill='#333355')

    # メインタイトル
    title_font = fit_text_font(draw, title, "W8", 120, FPW - 200)
    draw.text((FPW // 2, cy - 60), title, fill='white', font=title_font, anchor="mm")

    # サブタイトル
    if subtitle:
        subtitle = truncate_text(subtitle, TEXT_LIMITS["section_header"]["subtitle"])
        sub_font = fit_text_font(draw, subtitle, "W6", 48, FPW - 300)
        draw.text((FPW // 2, cy + 60), subtitle, fill='#AAAACC', font=sub_font, anchor="mm")

    return img


def create_sns_quote_panel(title, items):
    """SNS引用カードパネル（1920x1080）。X/Twitter風のカードUIを複数表示。"""
    img = Image.new('RGB', (FPW, FPH), (25, 25, 35))
    draw = ImageDraw.Draw(img)

    # ヘッダー
    if title:
        title = truncate_text(title, 20)
        header_font = fit_text_font(draw, title, "W8", 56, FPW - 200)
        draw.text((FPW // 2, 50), title, fill='white', font=header_font, anchor="mm")

    # SNSカード（最大3件表示）
    card_w = FPW - 200  # 1720px
    card_h = 240
    card_x = 100
    card_y_start = 120
    card_gap = 30

    for i, item in enumerate(items[:3]):
        cy = card_y_start + i * (card_h + card_gap)

        # カード背景（角丸風: 白背景）
        draw.rounded_rectangle(
            [card_x, cy, card_x + card_w, cy + card_h],
            radius=16, fill='#FFFFFF'
        )

        # ユーザー名（@表示）
        username = item.get("username", "user")
        username = truncate_text(username, TEXT_LIMITS["sns_quote"]["username"])
        name_font = get_font("W8", 36)
        display_name = username if username.startswith("@") else f"@{username}"
        draw.text((card_x + 30, cy + 20), display_name, fill='#1DA1F2', font=name_font)

        # タイムスタンプ
        timestamp = item.get("timestamp", "")
        if timestamp:
            ts_font = get_font("W3", 28)
            draw.text((card_x + card_w - 30, cy + 25), timestamp, fill='#999999',
                       font=ts_font, anchor="rm")

        # 本文
        text = item.get("text", "")
        text = truncate_text(text, TEXT_LIMITS["sns_quote"]["text"])
        text_font = fit_text_font(draw, text, "W6", 38, card_w - 60, min_size=24)
        # 自動改行
        lines = []
        current = ""
        for ch in text:
            test = current + ch
            bbox = draw.textbbox((0, 0), test, font=text_font)
            if bbox[2] - bbox[0] > card_w - 60:
                lines.append(current)
                current = ch
            else:
                current = test
        if current:
            lines.append(current)

        ty = cy + 75
        for line in lines[:3]:
            draw.text((card_x + 30, ty), line, fill='#333333', font=text_font)
            ty += 50

        # いいね数
        likes = item.get("likes", "")
        if likes:
            like_font = get_font("W6", 28)
            draw.text((card_x + 30, cy + card_h - 40), f"♥ {likes}", fill='#E91E63', font=like_font)

    return img


def create_fullscreen_summary_panel(title, items, cta_text=None):
    """フルスクリーンまとめパネル（1920x1080）。番号付きリストで重要ポイントを表示。"""
    img = Image.new('RGB', (FPW, FPH), (18, 18, 48))
    draw = ImageDraw.Draw(img)

    title = truncate_text(title, TEXT_LIMITS["fullscreen_summary"]["title"])

    # ヘッダー（赤帯）
    draw.rectangle([0, 0, FPW, 100], fill='#D93025')
    header_font = fit_text_font(draw, title, "W8", 60, FPW - 200)
    draw.text((FPW // 2, 50), title, fill='white', font=header_font, anchor="mm")

    # アイテムリスト（最大5件）
    badge_colors = ['#D93025', '#E8710A', '#9334E6', '#188038', '#1A73E8']
    item_y = 150
    item_h = 140

    for i, item in enumerate(items[:5]):
        y = item_y + i * item_h
        text = item if isinstance(item, str) else item.get("text", item.get("title", ""))
        text = truncate_text(text, TEXT_LIMITS["fullscreen_summary"]["item_text"])

        # 番号バッジ
        badge_color = badge_colors[i % len(badge_colors)]
        badge_r = 35
        badge_cx = 150
        badge_cy = y + item_h // 2
        draw.ellipse([badge_cx - badge_r, badge_cy - badge_r,
                      badge_cx + badge_r, badge_cy + badge_r], fill=badge_color)
        badge_font = get_font("W8", 40)
        draw.text((badge_cx, badge_cy), str(i + 1), fill='white', font=badge_font, anchor="mm")

        # テキスト
        text_font = fit_text_font(draw, text, "W6", 48, FPW - 350, min_size=28)
        draw.text((220, badge_cy), text, fill='white', font=text_font, anchor="lm")

        # 区切り線
        if i < len(items) - 1:
            draw.rectangle([150, y + item_h - 2, FPW - 150, y + item_h], fill='#333355')

    # CTA（コールトゥアクション）
    if cta_text:
        cta_font = get_font("W8", 44)
        draw.text((FPW // 2, FPH - 60), cta_text, fill='#FFD700', font=cta_font, anchor="mm")

    return img


# ============================================================
# グラフ系パネル（1344x756）
# ============================================================
TEXT_LIMITS["bar_chart"] = {"title": 18, "label": 10, "value_text": 8}
TEXT_LIMITS["pie_chart"] = {"title": 18, "label": 10}
TEXT_LIMITS["comparison"] = {"title": 18, "label": 10, "value": 12}

import math


def create_bar_chart_panel(title, items):
    """横棒グラフパネル。items: [{"label": "中国", "value": 70, "max_value": 100, "color": "#F44336"}]"""
    limits = TEXT_LIMITS["bar_chart"]
    title = truncate_text(title, limits["title"])

    img = Image.new('RGB', (PW, PH), '#1A1A2E')
    draw = ImageDraw.Draw(img)

    # ヘッダー（赤帯）
    draw.rectangle([0, 0, PW, 70], fill='#D93025')
    title_font = fit_text_font(draw, title, "W8", 44, PW - 60)
    draw.text((PW // 2, 35), title, fill='#FFFFFF', font=title_font, anchor="mm")

    num_items = min(len(items), 5)
    bar_area_top = 100
    bar_area_h = PH - bar_area_top - 30
    bar_h = min(80, (bar_area_h - (num_items - 1) * 15) // max(num_items, 1))
    total_h = num_items * bar_h + (num_items - 1) * 15
    start_y = bar_area_top + (bar_area_h - total_h) // 2

    label_w = 180
    value_w = 200
    bar_x = label_w + 20
    bar_max_w = PW - bar_x - value_w - 40

    max_val = max((item.get("max_value", item.get("value", 100)) for item in items[:num_items]), default=100)

    for i, item in enumerate(items[:num_items]):
        y = start_y + i * (bar_h + 15)
        label = truncate_text(item.get("label", ""), limits["label"])
        value = item.get("value", 0)
        color = item.get("color", ACCENT_COLORS[i % len(ACCENT_COLORS)])
        value_text = truncate_text(item.get("value_text", str(value)), limits["value_text"])

        # ラベル
        label_font = get_font("W8", 36)
        draw.text((label_w, y + bar_h // 2), label, fill='#FFFFFF', font=label_font, anchor="rm")

        # バー背景
        draw.rounded_rectangle([bar_x, y, bar_x + bar_max_w, y + bar_h], radius=8, fill='#2A2A4A')

        # バー本体
        bar_w = int(bar_max_w * (value / max_val)) if max_val > 0 else 0
        if bar_w > 16:
            draw.rounded_rectangle([bar_x, y, bar_x + bar_w, y + bar_h], radius=8, fill=color)

        # 値テキスト（バーの右側）
        vf = get_font("W8", 34)
        draw.text((bar_x + bar_max_w + 15, y + bar_h // 2), value_text, fill=color, font=vf, anchor="lm")

    return img


def create_pie_chart_panel(title, items):
    """円グラフパネル。items: [{"label": "中国", "value": 90, "color": "#F44336"}]"""
    limits = TEXT_LIMITS["pie_chart"]
    title = truncate_text(title, limits["title"])

    img = Image.new('RGB', (PW, PH), '#1A1A2E')
    draw = ImageDraw.Draw(img)

    # ヘッダー
    draw.rectangle([0, 0, PW, 70], fill='#D93025')
    title_font = fit_text_font(draw, title, "W8", 44, PW - 60)
    draw.text((PW // 2, 35), title, fill='#FFFFFF', font=title_font, anchor="mm")

    # 円グラフ描画
    cx, cy = PW // 3, (PH + 70) // 2
    radius = min(PW // 3, (PH - 100)) // 2 - 20
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]

    total = sum(item.get("value", 0) for item in items)
    if total == 0:
        total = 1

    start_angle = -90
    for i, item in enumerate(items):
        value = item.get("value", 0)
        color = item.get("color", ACCENT_COLORS[i % len(ACCENT_COLORS)])
        sweep = 360 * value / total
        draw.pieslice(bbox, start_angle, start_angle + sweep, fill=color, outline='#1A1A2E', width=3)
        start_angle += sweep

    # 凡例（右側）
    legend_x = PW * 2 // 3 - 60
    legend_y_start = cy - len(items) * 45
    for i, item in enumerate(items):
        ly = legend_y_start + i * 90
        color = item.get("color", ACCENT_COLORS[i % len(ACCENT_COLORS)])
        label = truncate_text(item.get("label", ""), limits["label"])
        value = item.get("value", 0)
        pct = f"{value * 100 // total}%" if total > 0 else "0%"

        # 色ボックス
        draw.rounded_rectangle([legend_x, ly, legend_x + 40, ly + 40], radius=6, fill=color)
        # ラベル
        draw.text((legend_x + 55, ly + 20), label, fill='#FFFFFF', font=get_font("W6", 36), anchor="lm")
        # パーセント
        draw.text((legend_x + 55, ly + 60), pct, fill=color, font=get_font("W8", 40), anchor="lm")

    return img


def create_comparison_panel(title, items, **kwargs):
    """比較パネル（VS形式）。kwargs: left_label, left_value, right_label, right_value, or items[0] vs items[1]"""
    limits = TEXT_LIMITS["comparison"]
    title = truncate_text(title, limits["title"])

    img = Image.new('RGB', (PW, PH), '#1A1A2E')
    draw = ImageDraw.Draw(img)

    # ヘッダー
    draw.rectangle([0, 0, PW, 70], fill='#D93025')
    title_font = fit_text_font(draw, title, "W8", 44, PW - 60)
    draw.text((PW // 2, 35), title, fill='#FFFFFF', font=title_font, anchor="mm")

    # 左右の値を取得
    if len(items) >= 2:
        left = items[0]
        right = items[1]
    else:
        left = {"label": kwargs.get("left_label", "A"), "value": kwargs.get("left_value", "?")}
        right = {"label": kwargs.get("right_label", "B"), "value": kwargs.get("right_value", "?")}

    left_label = truncate_text(left.get("label", ""), limits["label"])
    left_value = truncate_text(str(left.get("value", "")), limits["value"])
    left_color = left.get("color", "#1A73E8")
    right_label = truncate_text(right.get("label", ""), limits["label"])
    right_value = truncate_text(str(right.get("value", "")), limits["value"])
    right_color = right.get("color", "#F44336")

    mid_y = (PH + 70) // 2
    quarter_w = PW // 4

    # 左側ボックス
    lx = quarter_w
    draw.rounded_rectangle([lx - 200, mid_y - 140, lx + 200, mid_y + 140], radius=20, fill='#0D1B2A')
    draw.rounded_rectangle([lx - 198, mid_y - 138, lx + 198, mid_y + 138], radius=20, outline=left_color, width=4)
    lv_font = fit_text_font(draw, left_value, "W8", 72, 360)
    draw.text((lx, mid_y - 20), left_value, fill=left_color, font=lv_font, anchor="mm")
    ll_font = fit_text_font(draw, left_label, "W6", 40, 360)
    draw.text((lx, mid_y + 80), left_label, fill='#AAAACC', font=ll_font, anchor="mm")

    # VS
    vs_font = get_font("W8", 64)
    draw.text((PW // 2, mid_y), "VS", fill='#FFD700', font=vs_font, anchor="mm")

    # 右側ボックス
    rx = PW - quarter_w
    draw.rounded_rectangle([rx - 200, mid_y - 140, rx + 200, mid_y + 140], radius=20, fill='#0D1B2A')
    draw.rounded_rectangle([rx - 198, mid_y - 138, rx + 198, mid_y + 138], radius=20, outline=right_color, width=4)
    rv_font = fit_text_font(draw, right_value, "W8", 72, 360)
    draw.text((rx, mid_y - 20), right_value, fill=right_color, font=rv_font, anchor="mm")
    rl_font = fit_text_font(draw, right_label, "W6", 40, 360)
    draw.text((rx, mid_y + 80), right_label, fill='#AAAACC', font=rl_font, anchor="mm")

    # ハイライトテキスト（下部）
    highlight = kwargs.get("highlight")
    if highlight:
        hl_font = fit_text_font(draw, highlight, "W8", 36, PW - 100)
        draw.text((PW // 2, PH - 40), highlight, fill='#FFD700', font=hl_font, anchor="mm")

    return img


# ============================================================
# 縦パネル（1080x1920）— Shorts用グラフ重視デザイン
# ============================================================
VPW, VPH = 1080, 1920  # Vertical Panel size

TEXT_LIMITS["v_bar_chart"] = {"title": 14, "label": 8, "value_text": 8}
TEXT_LIMITS["v_pie_chart"] = {"title": 14, "label": 8}
TEXT_LIMITS["v_comparison"] = {"title": 14, "label": 8, "value": 10}
TEXT_LIMITS["v_summary"] = {"title": 12, "item_text": 20}


def create_v_bar_chart_panel(title, items):
    """縦型棒グラフパネル（1080x1920）。グラフが画面の大部分を占める。"""
    limits = TEXT_LIMITS["v_bar_chart"]
    title = truncate_text(title, limits["title"])

    img = Image.new('RGB', (VPW, VPH), '#1A1A2E')
    draw = ImageDraw.Draw(img)

    # ヘッダー（赤帯・コンパクト）
    draw.rectangle([0, 0, VPW, 120], fill='#D93025')
    title_font = fit_text_font(draw, title, "W8", 64, VPW - 80)
    draw.text((VPW // 2, 60), title, fill='#FFFFFF', font=title_font, anchor="mm")

    num_items = min(len(items), 8)  # 縦長なので最大8本
    bar_area_top = 180
    bar_area_h = VPH - bar_area_top - 60
    bar_h = min(120, (bar_area_h - (num_items - 1) * 25) // max(num_items, 1))
    total_h = num_items * bar_h + (num_items - 1) * 25
    start_y = bar_area_top + (bar_area_h - total_h) // 2

    label_w = 200
    value_w = 180
    bar_x = label_w + 30
    bar_max_w = VPW - bar_x - value_w - 40

    max_val = max((item.get("max_value", item.get("value", 100)) for item in items[:num_items]), default=100)

    for i, item in enumerate(items[:num_items]):
        y = start_y + i * (bar_h + 25)
        label = truncate_text(item.get("label", ""), limits["label"])
        value = item.get("value", 0)
        color = item.get("color", ACCENT_COLORS[i % len(ACCENT_COLORS)])
        value_text = truncate_text(item.get("value_text", str(value)), limits["value_text"])

        # ラベル（大きめフォント）
        label_font = fit_text_font(draw, label, "W8", 48, label_w - 10)
        draw.text((label_w, y + bar_h // 2), label, fill='#FFFFFF', font=label_font, anchor="rm")

        # バー背景
        draw.rounded_rectangle([bar_x, y, bar_x + bar_max_w, y + bar_h], radius=12, fill='#2A2A4A')

        # バー本体
        bar_w = int(bar_max_w * (value / max_val)) if max_val > 0 else 0
        if bar_w > 20:
            draw.rounded_rectangle([bar_x, y, bar_x + bar_w, y + bar_h], radius=12, fill=color)

        # 値テキスト（バーの右側、大きめ）
        vf = fit_text_font(draw, value_text, "W8", 44, value_w - 10)
        draw.text((bar_x + bar_max_w + 15, y + bar_h // 2), value_text, fill=color, font=vf, anchor="lm")

    return img


def create_v_pie_chart_panel(title, items):
    """縦型円グラフパネル（1080x1920）。円グラフ上部・凡例下部。"""
    limits = TEXT_LIMITS["v_pie_chart"]
    title = truncate_text(title, limits["title"])

    img = Image.new('RGB', (VPW, VPH), '#1A1A2E')
    draw = ImageDraw.Draw(img)

    # ヘッダー
    draw.rectangle([0, 0, VPW, 120], fill='#D93025')
    title_font = fit_text_font(draw, title, "W8", 64, VPW - 80)
    draw.text((VPW // 2, 60), title, fill='#FFFFFF', font=title_font, anchor="mm")

    # 円グラフ（上部中央に大きく配置）
    cx, cy = VPW // 2, 620
    radius = 380
    bbox = [cx - radius, cy - radius, cx + radius, cy + radius]

    total = sum(item.get("value", 0) for item in items)
    if total == 0:
        total = 1

    start_angle = -90
    for i, item in enumerate(items):
        value = item.get("value", 0)
        color = item.get("color", ACCENT_COLORS[i % len(ACCENT_COLORS)])
        sweep = 360 * value / total
        draw.pieslice(bbox, start_angle, start_angle + sweep, fill=color, outline='#1A1A2E', width=4)

        # パーセントラベルをパイ内に表示
        if sweep > 15:  # 小さすぎるセグメントにはラベルなし
            mid_angle = math.radians(start_angle + sweep / 2)
            label_r = radius * 0.65
            lx = cx + label_r * math.cos(mid_angle)
            ly = cy + label_r * math.sin(mid_angle)
            pct = f"{value * 100 // total}%"
            pct_font = get_font("W8", 44)
            draw.text((int(lx), int(ly)), pct, fill='#FFFFFF', font=pct_font, anchor="mm")

        start_angle += sweep

    # 凡例（下部に横並び2列）
    legend_top = cy + radius + 60
    cols = 2
    col_w = VPW // cols
    for i, item in enumerate(items):
        col = i % cols
        row = i // cols
        lx = col * col_w + col_w // 2
        ly = legend_top + row * 100

        color = item.get("color", ACCENT_COLORS[i % len(ACCENT_COLORS)])
        label = truncate_text(item.get("label", ""), limits["label"])

        # 色ボックス + ラベル
        draw.rounded_rectangle([lx - 140, ly, lx - 90, ly + 50], radius=8, fill=color)
        draw.text((lx - 75, ly + 25), label, fill='#FFFFFF', font=get_font("W6", 44), anchor="lm")

    return img


def create_v_comparison_panel(title, items, **kwargs):
    """縦型比較パネル（1080x1920）。上下に大きくVS表示。"""
    limits = TEXT_LIMITS["v_comparison"]
    title = truncate_text(title, limits["title"])

    img = Image.new('RGB', (VPW, VPH), '#1A1A2E')
    draw = ImageDraw.Draw(img)

    # ヘッダー
    draw.rectangle([0, 0, VPW, 120], fill='#D93025')
    title_font = fit_text_font(draw, title, "W8", 64, VPW - 80)
    draw.text((VPW // 2, 60), title, fill='#FFFFFF', font=title_font, anchor="mm")

    # 左右→上下に配置
    if len(items) >= 2:
        top = items[0]
        bottom = items[1]
    else:
        top = {"label": kwargs.get("left_label", "A"), "value": kwargs.get("left_value", "?")}
        bottom = {"label": kwargs.get("right_label", "B"), "value": kwargs.get("right_value", "?")}

    top_label = truncate_text(top.get("label", ""), limits["label"])
    top_value = truncate_text(str(top.get("value", "")), limits["value"])
    top_color = top.get("color", "#1A73E8")
    bottom_label = truncate_text(bottom.get("label", ""), limits["label"])
    bottom_value = truncate_text(str(bottom.get("value", "")), limits["value"])
    bottom_color = bottom.get("color", "#F44336")

    box_w, box_h = 800, 500
    box_x = (VPW - box_w) // 2

    # 上ボックス
    top_y = 250
    draw.rounded_rectangle([box_x, top_y, box_x + box_w, top_y + box_h], radius=30, fill='#0D1B2A')
    draw.rounded_rectangle([box_x + 3, top_y + 3, box_x + box_w - 3, top_y + box_h - 3], radius=30, outline=top_color, width=6)
    tv_font = fit_text_font(draw, top_value, "W8", 120, box_w - 80)
    draw.text((VPW // 2, top_y + box_h // 2 - 40), top_value, fill=top_color, font=tv_font, anchor="mm")
    tl_font = fit_text_font(draw, top_label, "W6", 56, box_w - 80)
    draw.text((VPW // 2, top_y + box_h // 2 + 80), top_label, fill='#AAAACC', font=tl_font, anchor="mm")

    # VS
    vs_y = top_y + box_h + 60
    vs_font = get_font("W8", 100)
    draw.text((VPW // 2, vs_y), "VS", fill='#FFD700', font=vs_font, anchor="mm")

    # 下ボックス
    bot_y = vs_y + 60
    draw.rounded_rectangle([box_x, bot_y, box_x + box_w, bot_y + box_h], radius=30, fill='#0D1B2A')
    draw.rounded_rectangle([box_x + 3, bot_y + 3, box_x + box_w - 3, bot_y + box_h - 3], radius=30, outline=bottom_color, width=6)
    bv_font = fit_text_font(draw, bottom_value, "W8", 120, box_w - 80)
    draw.text((VPW // 2, bot_y + box_h // 2 - 40), bottom_value, fill=bottom_color, font=bv_font, anchor="mm")
    bl_font = fit_text_font(draw, bottom_label, "W6", 56, box_w - 80)
    draw.text((VPW // 2, bot_y + box_h // 2 + 80), bottom_label, fill='#AAAACC', font=bl_font, anchor="mm")

    # ハイライトテキスト（最下部）
    highlight = kwargs.get("highlight")
    if highlight:
        hl_font = fit_text_font(draw, highlight, "W8", 48, VPW - 100)
        draw.text((VPW // 2, VPH - 80), highlight, fill='#FFD700', font=hl_font, anchor="mm")

    return img


def create_v_summary_panel(title, items, cta_text=None):
    """縦型まとめパネル（1080x1920）。大きな番号+テキストのシンプルリスト。"""
    limits = TEXT_LIMITS["v_summary"]
    title = truncate_text(title, limits["title"])

    img = Image.new('RGB', (VPW, VPH), '#1A1A1A')
    draw = ImageDraw.Draw(img)

    # ヘッダー（赤）
    draw.rectangle([0, 0, VPW, 120], fill='#D32F2F')
    title_font = fit_text_font(draw, title, "W8", 64, VPW - 80)
    draw.text((VPW // 2, 60), title, fill='#FFFFFF', font=title_font, anchor="mm")

    num_items = min(len(items), 5)
    item_area_top = 200
    item_area_h = VPH - item_area_top - (160 if cta_text else 60)
    item_h = min(280, (item_area_h - (num_items - 1) * 30) // max(num_items, 1))
    total_h = num_items * item_h + (num_items - 1) * 30
    start_y = item_area_top + (item_area_h - total_h) // 2

    for i, item in enumerate(items[:num_items]):
        y = start_y + i * (item_h + 30)
        text = item if isinstance(item, str) else item.get("text", item.get("label", ""))
        text = truncate_text(text, limits["item_text"])

        badge_color = ACCENT_COLORS[i % len(ACCENT_COLORS)]

        # カード背景
        draw.rounded_rectangle([60, y, VPW - 60, y + item_h], radius=20, fill='#1E2A47')
        draw.rounded_rectangle([60, y, VPW - 60, y + item_h], radius=20, outline=badge_color, width=4)

        # 番号バッジ（大きめ）
        badge_r = 45
        badge_cx = 140
        badge_cy = y + item_h // 2
        draw.ellipse([badge_cx - badge_r, badge_cy - badge_r,
                      badge_cx + badge_r, badge_cy + badge_r], fill=badge_color)
        draw.text((badge_cx, badge_cy), str(i + 1), fill='#FFFFFF', font=get_font("W8", 52), anchor="mm")

        # テキスト（大きめフォント）
        text_font = fit_text_font(draw, text, "W6", 48, VPW - 300, min_size=28)
        draw.text((230, badge_cy), text, fill='#E0E0E0', font=text_font, anchor="lm")

    # CTA
    if cta_text:
        cta_font = fit_text_font(draw, cta_text, "W8", 56, VPW - 200)
        draw.text((VPW // 2, VPH - 80), cta_text, fill='#FF9800', font=cta_font, anchor="mm")

    return img


def create_panel(filename, title, layout, items, vertical=False, **kwargs):
    """パネル生成のルーター。vertical=Trueで1080x1920縦パネル。"""
    # 縦パネルモード: グラフ系+summaryは縦版を使用
    if vertical:
        if layout == "bar_chart":
            img = create_v_bar_chart_panel(title, items)
        elif layout == "pie_chart":
            img = create_v_pie_chart_panel(title, items)
        elif layout == "comparison":
            img = create_v_comparison_panel(title, items, **kwargs)
        elif layout == "summary":
            cta_text = kwargs.get("cta_text")
            img = create_v_summary_panel(title, items, cta_text)
        else:
            # 縦版未対応のレイアウトはフォールバック（横版で生成）
            print(f"  ! 縦版未対応のレイアウト「{layout}」→ 横版で生成", file=sys.stderr)
            return create_panel(filename, title, layout, items, vertical=False, **kwargs)

        output_path = PANELS_DIR / filename
        img.save(output_path)
        print(f"  + {filename} (vertical 1080x1920)")
        return

    # 横パネルモード（従来通り）
    if layout == "timeline":
        footer_text = kwargs.get("footer_text")
        footer_highlight = kwargs.get("footer_highlight")
        img = create_timeline_panel(title, items, footer_text, footer_highlight)
    elif layout == "summary":
        cta_text = kwargs.get("cta_text")
        img = create_summary_panel(title, items, cta_text)
    elif layout == "title_card":
        subtitle = kwargs.get("subtitle", "")
        main_text = kwargs.get("main_text", "")
        footer_text = kwargs.get("footer_text")
        img = create_title_card_panel(title, subtitle, main_text, footer_text)
    elif layout == "detail_list":
        img = create_detail_list_panel(title, items)
    elif layout == "section_header":
        subtitle = kwargs.get("subtitle", "")
        img = create_section_header_panel(title, subtitle)
    elif layout == "sns_quote":
        img = create_sns_quote_panel(title, items)
    elif layout == "fullscreen_summary":
        cta_text = kwargs.get("cta_text")
        img = create_fullscreen_summary_panel(title, items, cta_text)
    elif layout == "bar_chart":
        img = create_bar_chart_panel(title, items)
    elif layout == "pie_chart":
        img = create_pie_chart_panel(title, items)
    elif layout == "comparison":
        img = create_comparison_panel(title, items, **kwargs)
    else:
        print(f"  ! 未対応のレイアウト: {layout}", file=sys.stderr)
        return

    output_path = PANELS_DIR / filename
    img.save(output_path)
    print(f"  + {filename}")


def main():
    """標準入力からJSONを読み取ってパネルを生成

    使い方:
        cat panels.json | python3 create_data_panels_v7.py [--vertical]
        --vertical: Shorts用1080x1920縦パネルを生成（グラフ重視・文字最小限）
    """
    vertical = "--vertical" in sys.argv

    try:
        panels_data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"  X JSON解析エラー: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(panels_data, list):
        print("  X JSONはリスト形式である必要があります", file=sys.stderr)
        sys.exit(1)

    mode = "vertical 1080x1920" if vertical else "horizontal 1344x756"
    print(f"パネル生成開始: {len(panels_data)}枚 ({mode})")

    for panel in panels_data:
        filename = panel.get("filename")
        title = panel.get("title", "無題")
        layout = panel.get("layout", "summary")
        items = panel.get("items", [])

        if not filename:
            print(f"  ! スキップ（filename未指定）: {title}", file=sys.stderr)
            continue

        kwargs = {
            "cta_text": panel.get("cta_text"),
            "subtitle": panel.get("subtitle"),
            "main_text": panel.get("main_text"),
            "footer_text": panel.get("footer_text"),
            "footer_highlight": panel.get("footer_highlight"),
            "highlight": panel.get("highlight"),
            "left_label": panel.get("left_label"),
            "left_value": panel.get("left_value"),
            "right_label": panel.get("right_label"),
            "right_value": panel.get("right_value"),
        }

        create_panel(filename, title, layout, items, vertical=vertical, **kwargs)

    print(f"\n完了: {len(panels_data)}枚のパネルを生成 -> {PANELS_DIR}")


if __name__ == "__main__":
    main()
