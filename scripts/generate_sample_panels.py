#!/usr/bin/env python3
"""
エイミー先生の経済学 — サンプルパネル生成（2パターン比較）
パターンA: チビキャラ＋国旗バッジ（Pillow描画）
パターンB: 絵文字コンポジション（pilmoji使用）
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pilmoji import Pilmoji
from pathlib import Path
import json

# === 設定 ===
PROJECT_ROOT = Path(__file__).parent.parent
SAMPLES_DIR = PROJECT_ROOT / "samples" / "スタグフレーション"
SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

# パネルサイズ（16:9メインコンテンツ）
PANEL_W, PANEL_H = 1080, 608

# Shortsフレーム
SHORTS_W, SHORTS_H = 1080, 1920
TOP_BAR_H = 270
BOTTOM_BAR_H = 270

# フォント
def get_font(weight="W6", size=32):
    path = f"/System/Library/Fonts/ヒラギノ角ゴシック {weight}.ttc"
    return ImageFont.truetype(path, size)

# カラーパレット
COLORS = {
    "bg_dark": "#1A1A2E",
    "bg_panel": "#16213E",
    "accent_red": "#E94560",
    "accent_yellow": "#FFD93D",
    "accent_blue": "#4ECDC4",
    "accent_green": "#45B7A0",
    "text_white": "#FFFFFF",
    "text_gray": "#B0B0B0",
    "bar_top": "#0F3460",
    "bar_bottom": "#16213E",
}

def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


# =============================================
# パターンB: 絵文字コンポジション
# =============================================

def create_emoji_panel_1(output_path):
    """パネル1: タイトルカード — スタグフレーションとは？"""
    img = Image.new("RGB", (PANEL_W, PANEL_H), hex_to_rgb(COLORS["bg_dark"]))
    draw = ImageDraw.Draw(img)

    # 背景グラデーション風（上部に暗い帯）
    for y in range(80):
        alpha = int(60 * (1 - y / 80))
        draw.line([(0, y), (PANEL_W, y)], fill=(15, 52, 96, alpha)[:3])

    with Pilmoji(img) as pmj:
        # メインタイトル
        pmj.text((PANEL_W // 2 - 320, 40), "📉 スタグフレーション 📈",
                 font=get_font("W8", 44), fill=hex_to_rgb(COLORS["accent_yellow"]))

        # 中央の図解
        # 左側: 物価上昇
        pmj.text((100, 160), "🛒💰⬆️", font=get_font("W6", 72))
        pmj.text((100, 260), "物価が上がる", font=get_font("W6", 32),
                 fill=hex_to_rgb(COLORS["accent_red"]))

        # 中央: ×マーク
        pmj.text((PANEL_W // 2 - 40, 180), "✖️", font=get_font("W8", 80))

        # 右側: 景気停滞
        pmj.text((650, 160), "🏭📊⬇️", font=get_font("W6", 72))
        pmj.text((650, 260), "景気が停滞", font=get_font("W6", 32),
                 fill=hex_to_rgb(COLORS["accent_blue"]))

        # 下部: 結論
        draw.rounded_rectangle([(80, 360), (PANEL_W - 80, 450)],
                               radius=15, fill=hex_to_rgb(COLORS["accent_red"]))
        pmj.text((PANEL_W // 2 - 280, 375), "😱 最悪の組み合わせ 😱",
                 font=get_font("W8", 44), fill=(255, 255, 255))

        # サブテキスト
        pmj.text((PANEL_W // 2 - 260, 480), "給料は上がらないのに出費だけ増える",
                 font=get_font("W6", 30), fill=hex_to_rgb(COLORS["text_gray"]))

        # 下部アクセント
        pmj.text((PANEL_W // 2 - 180, 540), "💴↗️  🍚↗️  ⛽↗️  ⚡↗️",
                 font=get_font("W6", 36))

    img.save(output_path, quality=95)
    return output_path


def create_emoji_panel_2(output_path):
    """パネル2: 原油高＋円安のダブルパンチ"""
    img = Image.new("RGB", (PANEL_W, PANEL_H), hex_to_rgb(COLORS["bg_dark"]))
    draw = ImageDraw.Draw(img)

    with Pilmoji(img) as pmj:
        # タイトル
        pmj.text((PANEL_W // 2 - 280, 30), "⚡ ダブルパンチの構造 ⚡",
                 font=get_font("W8", 40), fill=hex_to_rgb(COLORS["accent_yellow"]))

        # 左ボックス: 原油高
        draw.rounded_rectangle([(40, 110), (510, 340)],
                               radius=20, fill=(30, 30, 60))
        draw.rounded_rectangle([(40, 110), (510, 170)],
                               radius=20, fill=hex_to_rgb(COLORS["accent_red"]))
        # 下部の角を埋める
        draw.rectangle([(40, 155), (510, 170)], fill=hex_to_rgb(COLORS["accent_red"]))
        pmj.text((140, 118), "🛢️ 原油価格高騰", font=get_font("W8", 34),
                 fill=(255, 255, 255))
        pmj.text((70, 190), "1バレル = $120", font=get_font("W6", 36),
                 fill=hex_to_rgb(COLORS["accent_red"]))
        pmj.text((70, 250), "🇸🇦🇷🇺 産油国の減産", font=get_font("W6", 26),
                 fill=hex_to_rgb(COLORS["text_gray"]))
        pmj.text((70, 290), "🇮🇷 中東情勢の緊迫化", font=get_font("W6", 26),
                 fill=hex_to_rgb(COLORS["text_gray"]))

        # 右ボックス: 円安
        draw.rounded_rectangle([(560, 110), (1040, 340)],
                               radius=20, fill=(30, 30, 60))
        draw.rounded_rectangle([(560, 110), (1040, 170)],
                               radius=20, fill=hex_to_rgb(COLORS["accent_blue"]))
        draw.rectangle([(560, 155), (1040, 170)], fill=hex_to_rgb(COLORS["accent_blue"]))
        pmj.text((670, 118), "💴 円安進行", font=get_font("W8", 34),
                 fill=(255, 255, 255))
        pmj.text((590, 190), "1ドル = ¥160", font=get_font("W6", 36),
                 fill=hex_to_rgb(COLORS["accent_blue"]))
        pmj.text((590, 250), "🇺🇸 米国の高金利維持", font=get_font("W6", 26),
                 fill=hex_to_rgb(COLORS["text_gray"]))
        pmj.text((590, 290), "🇯🇵 日銀の利上げ躊躇", font=get_font("W6", 26),
                 fill=hex_to_rgb(COLORS["text_gray"]))

        # 合流矢印
        pmj.text((PANEL_W // 2 - 30, 350), "⬇️", font=get_font("W6", 48))

        # 結果ボックス
        draw.rounded_rectangle([(150, 420), (930, 520)],
                               radius=15, fill=(80, 20, 20))
        pmj.text((200, 438), "🇯🇵 輸入コスト爆増 → 家計を直撃！",
                 font=get_font("W8", 36), fill=(255, 255, 255))

        # 影響アイテム
        pmj.text((150, 545), "⛽+30%   🍞+25%   ⚡+20%   🥩+35%",
                 font=get_font("W6", 28), fill=hex_to_rgb(COLORS["accent_red"]))

    img.save(output_path, quality=95)
    return output_path


def create_emoji_panel_3(output_path):
    """パネル3: 日銀のジレンマ"""
    img = Image.new("RGB", (PANEL_W, PANEL_H), hex_to_rgb(COLORS["bg_dark"]))
    draw = ImageDraw.Draw(img)

    with Pilmoji(img) as pmj:
        # タイトル
        pmj.text((PANEL_W // 2 - 250, 30), "🏛️ 日銀のジレンマ 🏛️",
                 font=get_font("W8", 40), fill=hex_to_rgb(COLORS["accent_yellow"]))

        # 左選択肢: 金利を上げる
        draw.rounded_rectangle([(40, 110), (510, 380)],
                               radius=20, fill=(20, 50, 20))
        pmj.text((100, 125), "選択肢A: 金利を上げる",
                 font=get_font("W8", 28), fill=hex_to_rgb(COLORS["accent_green"]))
        pmj.text((70, 180), "📈 円安は止まる", font=get_font("W6", 28),
                 fill=(255, 255, 255))
        pmj.text((70, 230), "BUT", font=get_font("W8", 32),
                 fill=hex_to_rgb(COLORS["accent_red"]))
        pmj.text((70, 280), "🏭💀 企業の借入コスト増",
                 font=get_font("W6", 26), fill=hex_to_rgb(COLORS["accent_red"]))
        pmj.text((70, 325), "📉😰 景気がさらに冷え込む",
                 font=get_font("W6", 26), fill=hex_to_rgb(COLORS["accent_red"]))

        # 中央 VS
        pmj.text((PANEL_W // 2 - 30, 220), "⚔️", font=get_font("W6", 56))

        # 右選択肢: 金利を据え置く
        draw.rounded_rectangle([(560, 110), (1040, 380)],
                               radius=20, fill=(50, 20, 20))
        pmj.text((610, 125), "選択肢B: 金利を据え置く",
                 font=get_font("W8", 28), fill=hex_to_rgb(COLORS["accent_red"]))
        pmj.text((590, 180), "🏭✨ 企業は助かる", font=get_font("W6", 28),
                 fill=(255, 255, 255))
        pmj.text((590, 230), "BUT", font=get_font("W8", 32),
                 fill=hex_to_rgb(COLORS["accent_red"]))
        pmj.text((590, 280), "💴📉 円安がさらに進む",
                 font=get_font("W6", 26), fill=hex_to_rgb(COLORS["accent_red"]))
        pmj.text((590, 325), "🛒💸 物価がもっと上がる",
                 font=get_font("W6", 26), fill=hex_to_rgb(COLORS["accent_red"]))

        # 結論
        draw.rounded_rectangle([(150, 420), (930, 510)],
                               radius=15, fill=hex_to_rgb(COLORS["accent_red"]))
        pmj.text((220, 435), "😱 どちらに転んでもヤバい 😱",
                 font=get_font("W8", 40), fill=(255, 255, 255))

        pmj.text((PANEL_W // 2 - 260, 540), "→ だからこそ資産防衛の知識が必要！",
                 font=get_font("W6", 30), fill=hex_to_rgb(COLORS["accent_yellow"]))

    img.save(output_path, quality=95)
    return output_path


# =============================================
# パターンA: チビキャラ＋国旗バッジ（Pillow図形描画）
# =============================================

def draw_chibi(draw, x, y, scale=1.0, color="#FFD700", expression="normal", flag_emoji=None, img=None):
    """シンプルなチビキャラを描画"""
    s = scale
    head_r = int(35 * s)
    body_h = int(50 * s)
    body_w = int(40 * s)

    # 体（丸い四角形）
    body_color = hex_to_rgb(color)
    draw.rounded_rectangle(
        [(x - body_w//2, y + head_r), (x + body_w//2, y + head_r + body_h)],
        radius=10, fill=body_color
    )

    # 頭（円）
    skin = (255, 220, 185)
    draw.ellipse(
        [(x - head_r, y - head_r), (x + head_r, y + head_r)],
        fill=skin, outline=(200, 170, 140), width=2
    )

    # 目
    eye_y = y - int(5 * s)
    eye_offset = int(12 * s)
    eye_r = int(5 * s)
    draw.ellipse([(x - eye_offset - eye_r, eye_y - eye_r),
                  (x - eye_offset + eye_r, eye_y + eye_r)], fill=(40, 40, 40))
    draw.ellipse([(x + eye_offset - eye_r, eye_y - eye_r),
                  (x + eye_offset + eye_r, eye_y + eye_r)], fill=(40, 40, 40))

    # 目のハイライト
    hl_r = int(2 * s)
    draw.ellipse([(x - eye_offset - hl_r + 2, eye_y - hl_r - 1),
                  (x - eye_offset + hl_r + 2, eye_y + hl_r - 1)], fill=(255, 255, 255))
    draw.ellipse([(x + eye_offset - hl_r + 2, eye_y - hl_r - 1),
                  (x + eye_offset + hl_r + 2, eye_y + hl_r - 1)], fill=(255, 255, 255))

    # 表情
    mouth_y = y + int(12 * s)
    if expression == "shocked":
        draw.ellipse([(x - 6, mouth_y - 6), (x + 6, mouth_y + 6)], fill=(40, 40, 40))
    elif expression == "worried":
        draw.arc([(x - 10, mouth_y), (x + 10, mouth_y + 12)], 0, 180, fill=(40, 40, 40), width=2)
    elif expression == "smile":
        draw.arc([(x - 10, mouth_y - 6), (x + 10, mouth_y + 6)], 0, 180, fill=(40, 40, 40), width=2)
    else:
        draw.line([(x - 8, mouth_y), (x + 8, mouth_y)], fill=(40, 40, 40), width=2)

    # 国旗バッジ（絵文字）
    if flag_emoji and img:
        with Pilmoji(img) as pmj:
            pmj.text((x + head_r - 5, y - head_r - 5), flag_emoji,
                     font=get_font("W6", 24))


def create_chibi_panel_1(output_path):
    """パネル1: タイトルカード"""
    img = Image.new("RGB", (PANEL_W, PANEL_H), hex_to_rgb(COLORS["bg_dark"]))
    draw = ImageDraw.Draw(img)

    # ヘッダー帯
    draw.rectangle([(0, 0), (PANEL_W, 80)], fill=hex_to_rgb(COLORS["bar_top"]))
    draw.text((PANEL_W // 2 - 230, 15), "スタグフレーションとは？",
              font=get_font("W8", 44), fill=hex_to_rgb(COLORS["accent_yellow"]))

    # 左グループ: 物価上昇のチビキャラたち
    draw.rounded_rectangle([(40, 110), (510, 350)], radius=20, fill=(30, 30, 60))
    draw.text((170, 120), "物価が上がる", font=get_font("W8", 30),
              fill=hex_to_rgb(COLORS["accent_red"]))

    # 買い物する人（困り顔）
    draw_chibi(draw, 150, 240, scale=1.2, color="#E94560", expression="worried")
    draw_chibi(draw, 280, 250, scale=1.0, color="#FF8C00", expression="shocked")
    draw_chibi(draw, 400, 240, scale=1.1, color="#DC143C", expression="worried")

    # 矢印（上向き）
    draw.text((220, 310), "↑↑↑", font=get_font("W8", 28),
              fill=hex_to_rgb(COLORS["accent_red"]))

    # 右グループ: 景気停滞のチビキャラたち
    draw.rounded_rectangle([(560, 110), (1040, 350)], radius=20, fill=(30, 30, 60))
    draw.text((700, 120), "景気が停滞", font=get_font("W8", 30),
              fill=hex_to_rgb(COLORS["accent_blue"]))

    # 工場の人たち（暗い顔）
    draw_chibi(draw, 670, 240, scale=1.2, color="#4682B4", expression="worried")
    draw_chibi(draw, 800, 250, scale=1.0, color="#5F9EA0", expression="worried")
    draw_chibi(draw, 930, 240, scale=1.1, color="#6495ED", expression="shocked")

    draw.text((740, 310), "↓↓↓", font=get_font("W8", 28),
              fill=hex_to_rgb(COLORS["accent_blue"]))

    # 中央 VS
    draw.text((PANEL_W // 2 - 20, 200), "×", font=get_font("W8", 48),
              fill=(255, 255, 255))

    # 結論帯
    draw.rounded_rectangle([(150, 380), (930, 460)],
                           radius=15, fill=hex_to_rgb(COLORS["accent_red"]))
    draw.text((250, 392), "最悪の組み合わせ！",
              font=get_font("W8", 44), fill=(255, 255, 255))

    # サブテキスト
    draw.text((PANEL_W // 2 - 260, 490), "給料は上がらないのに出費だけ増える",
              font=get_font("W6", 30), fill=hex_to_rgb(COLORS["text_gray"]))

    # 下部のアイコン（テキストベース）
    items = ["ガソリン↑", "食料品↑", "電気代↑", "家賃↑"]
    x_start = 120
    for i, item in enumerate(items):
        draw.rounded_rectangle(
            [(x_start + i * 230, 540), (x_start + i * 230 + 200, 585)],
            radius=10, fill=(60, 20, 20)
        )
        draw.text((x_start + i * 230 + 20, 548), item,
                  font=get_font("W6", 26), fill=hex_to_rgb(COLORS["accent_red"]))

    img.save(output_path, quality=95)
    return output_path


def create_chibi_panel_2(output_path):
    """パネル2: 原油高＋円安"""
    img = Image.new("RGB", (PANEL_W, PANEL_H), hex_to_rgb(COLORS["bg_dark"]))
    draw = ImageDraw.Draw(img)

    # ヘッダー
    draw.rectangle([(0, 0), (PANEL_W, 80)], fill=hex_to_rgb(COLORS["bar_top"]))
    draw.text((PANEL_W // 2 - 260, 15), "ダブルパンチの構造",
              font=get_font("W8", 44), fill=hex_to_rgb(COLORS["accent_yellow"]))

    # 左: 原油高ボックス
    draw.rounded_rectangle([(40, 100), (510, 330)], radius=20, fill=(50, 20, 20))
    draw.rounded_rectangle([(40, 100), (510, 155)], radius=20, fill=hex_to_rgb(COLORS["accent_red"]))
    draw.rectangle([(40, 140), (510, 155)], fill=hex_to_rgb(COLORS["accent_red"]))
    draw.text((140, 108), "原油価格高騰", font=get_font("W8", 34), fill=(255, 255, 255))

    draw.text((70, 175), "1バレル = $120", font=get_font("W6", 34),
              fill=hex_to_rgb(COLORS["accent_red"]))

    # 産油国のチビキャラ
    draw_chibi(draw, 120, 280, scale=0.8, color="#006C35", expression="smile", flag_emoji="🇸🇦", img=img)
    draw_chibi(draw, 250, 280, scale=0.8, color="#0039A6", expression="smile", flag_emoji="🇷🇺", img=img)
    draw_chibi(draw, 380, 280, scale=0.8, color="#239F40", expression="worried", flag_emoji="🇮🇷", img=img)

    # 右: 円安ボックス
    draw.rounded_rectangle([(560, 100), (1040, 330)], radius=20, fill=(20, 20, 60))
    draw.rounded_rectangle([(560, 100), (1040, 155)], radius=20, fill=hex_to_rgb(COLORS["accent_blue"]))
    draw.rectangle([(560, 140), (1040, 155)], fill=hex_to_rgb(COLORS["accent_blue"]))
    draw.text((700, 108), "円安進行", font=get_font("W8", 34), fill=(255, 255, 255))

    draw.text((590, 175), "1ドル = ¥160", font=get_font("W6", 34),
              fill=hex_to_rgb(COLORS["accent_blue"]))

    # 日米のチビキャラ
    draw_chibi(draw, 680, 280, scale=0.8, color="#BC002D", expression="worried", flag_emoji="🇯🇵", img=img)
    draw_chibi(draw, 870, 280, scale=0.8, color="#3C3B6E", expression="smile", flag_emoji="🇺🇸", img=img)

    # 合流矢印
    draw.text((PANEL_W // 2 - 20, 345), "▼", font=get_font("W8", 40),
              fill=(255, 255, 255))

    # 結果
    draw.rounded_rectangle([(100, 400), (980, 490)], radius=15, fill=(80, 20, 20))
    draw.text((150, 415), "日本の輸入コスト爆増 → 家計を直撃！",
              font=get_font("W8", 34), fill=(255, 255, 255))

    # 影響リスト
    impacts = [("ガソリン", "+30%"), ("食料品", "+25%"), ("電気代", "+20%"), ("牛肉", "+35%")]
    for i, (name, pct) in enumerate(impacts):
        x = 100 + i * 250
        draw.rounded_rectangle([(x, 520), (x + 220, 580)], radius=10, fill=(60, 20, 20))
        draw.text((x + 15, 530), f"{name} {pct}", font=get_font("W6", 26),
                  fill=hex_to_rgb(COLORS["accent_red"]))

    img.save(output_path, quality=95)
    return output_path


def create_chibi_panel_3(output_path):
    """パネル3: 日銀のジレンマ"""
    img = Image.new("RGB", (PANEL_W, PANEL_H), hex_to_rgb(COLORS["bg_dark"]))
    draw = ImageDraw.Draw(img)

    # ヘッダー
    draw.rectangle([(0, 0), (PANEL_W, 80)], fill=hex_to_rgb(COLORS["bar_top"]))
    draw.text((PANEL_W // 2 - 200, 15), "日銀のジレンマ",
              font=get_font("W8", 44), fill=hex_to_rgb(COLORS["accent_yellow"]))

    # 左: 金利を上げる
    draw.rounded_rectangle([(40, 100), (510, 380)], radius=20, fill=(20, 50, 20))
    draw.text((80, 110), "選択肢A: 金利を上げる", font=get_font("W8", 26),
              fill=hex_to_rgb(COLORS["accent_green"]))
    draw.text((70, 155), "→ 円安は止まる", font=get_font("W6", 26), fill=(255, 255, 255))
    draw.text((70, 200), "BUT", font=get_font("W8", 30),
              fill=hex_to_rgb(COLORS["accent_red"]))

    # 困っている企業チビキャラ
    draw_chibi(draw, 150, 300, scale=0.9, color="#4682B4", expression="shocked")
    draw_chibi(draw, 300, 310, scale=0.8, color="#5F9EA0", expression="worried")
    draw.text((380, 300), "💀", font=get_font("W6", 36))

    draw.text((70, 240), "企業の借入コスト増", font=get_font("W6", 24),
              fill=hex_to_rgb(COLORS["accent_red"]))
    draw.text((70, 275), "景気がさらに冷え込む", font=get_font("W6", 24),
              fill=hex_to_rgb(COLORS["accent_red"]))

    # 中央 VS
    draw.text((PANEL_W // 2 - 20, 220), "VS", font=get_font("W8", 36),
              fill=(255, 255, 255))

    # 右: 金利を据え置く
    draw.rounded_rectangle([(560, 100), (1040, 380)], radius=20, fill=(50, 20, 20))
    draw.text((590, 110), "選択肢B: 金利を据え置く", font=get_font("W8", 26),
              fill=hex_to_rgb(COLORS["accent_red"]))
    draw.text((590, 155), "→ 企業は助かる", font=get_font("W6", 26), fill=(255, 255, 255))
    draw.text((590, 200), "BUT", font=get_font("W8", 30),
              fill=hex_to_rgb(COLORS["accent_red"]))

    # 困っている消費者チビキャラ
    draw_chibi(draw, 680, 300, scale=0.9, color="#DC143C", expression="worried")
    draw_chibi(draw, 830, 310, scale=0.8, color="#FF6347", expression="shocked")
    draw.text((910, 300), "💸", font=get_font("W6", 36))

    draw.text((590, 240), "円安がさらに進む", font=get_font("W6", 24),
              fill=hex_to_rgb(COLORS["accent_red"]))
    draw.text((590, 275), "物価がもっと上がる", font=get_font("W6", 24),
              fill=hex_to_rgb(COLORS["accent_red"]))

    # 結論
    draw.rounded_rectangle([(150, 420), (930, 510)], radius=15,
                           fill=hex_to_rgb(COLORS["accent_red"]))
    draw.text((220, 435), "どちらに転んでもヤバい！",
              font=get_font("W8", 42), fill=(255, 255, 255))

    draw.text((PANEL_W // 2 - 280, 540), "→ だからこそ資産防衛の知識が必要！",
              font=get_font("W6", 30), fill=hex_to_rgb(COLORS["accent_yellow"]))

    img.save(output_path, quality=95)
    return output_path


# =============================================
# Shortsフレーム合成（16:9 → 9:16ラッピング）
# =============================================

def wrap_in_shorts_frame(panel_path, output_path, title_text, subtitle_text):
    """16:9パネルを9:16 Shortsフレームに合成"""
    frame = Image.new("RGB", (SHORTS_W, SHORTS_H), hex_to_rgb(COLORS["bg_dark"]))
    draw = ImageDraw.Draw(frame)

    # 上部バー
    draw.rectangle([(0, 0), (SHORTS_W, TOP_BAR_H)], fill=hex_to_rgb(COLORS["bar_top"]))

    with Pilmoji(frame) as pmj:
        # チャンネル名
        pmj.text((SHORTS_W // 2 - 260, 30), "👩‍🏫 エイミー先生の経済学",
                 font=get_font("W8", 38), fill=hex_to_rgb(COLORS["accent_yellow"]))

        # タイトル
        # タイトルが長い場合は自動改行
        if len(title_text) > 18:
            mid = len(title_text) // 2
            # なるべくスペースや句読点で区切る
            line1 = title_text[:mid]
            line2 = title_text[mid:]
            pmj.text((SHORTS_W // 2 - 350, 100), line1,
                     font=get_font("W8", 42), fill=(255, 255, 255))
            pmj.text((SHORTS_W // 2 - 350, 160), line2,
                     font=get_font("W8", 42), fill=(255, 255, 255))
        else:
            pmj.text((SHORTS_W // 2 - 300, 120), title_text,
                     font=get_font("W8", 46), fill=(255, 255, 255))

    # メインコンテンツ（16:9パネル）
    panel = Image.open(panel_path)
    panel = panel.resize((PANEL_W, PANEL_H), Image.LANCZOS)
    y_offset = TOP_BAR_H + (SHORTS_H - TOP_BAR_H - BOTTOM_BAR_H - PANEL_H) // 2
    frame.paste(panel, (0, y_offset))

    # 下部バー
    draw.rectangle([(0, SHORTS_H - BOTTOM_BAR_H), (SHORTS_W, SHORTS_H)],
                   fill=hex_to_rgb(COLORS["bar_bottom"]))

    # 字幕
    with Pilmoji(frame) as pmj:
        # 字幕テキスト（中央揃え風に）
        subtitle_font = get_font("W6", 34)
        # 簡易的な中央揃え
        if len(subtitle_text) > 22:
            mid = len(subtitle_text) // 2
            line1 = subtitle_text[:mid]
            line2 = subtitle_text[mid:]
            pmj.text((60, SHORTS_H - BOTTOM_BAR_H + 60), line1,
                     font=subtitle_font, fill=(255, 255, 255))
            pmj.text((60, SHORTS_H - BOTTOM_BAR_H + 110), line2,
                     font=subtitle_font, fill=(255, 255, 255))
        else:
            pmj.text((60, SHORTS_H - BOTTOM_BAR_H + 80), subtitle_text,
                     font=subtitle_font, fill=(255, 255, 255))

        # スピーカー名
        pmj.text((60, SHORTS_H - BOTTOM_BAR_H + 20), "👩‍🏫 エイミー先生",
                 font=get_font("W8", 28), fill=hex_to_rgb(COLORS["accent_yellow"]))

    frame.save(output_path, quality=95)
    return output_path


# =============================================
# メイン実行
# =============================================

if __name__ == "__main__":
    print("=" * 60)
    print("エイミー先生の経済学 — サンプルパネル生成")
    print("テーマ: スタグフレーション")
    print("=" * 60)

    # パターンB: 絵文字コンポジション
    print("\n--- パターンB: 絵文字コンポジション ---")
    p1 = create_emoji_panel_1(SAMPLES_DIR / "emoji_panel_01.jpg")
    print(f"  生成: {p1}")
    p2 = create_emoji_panel_2(SAMPLES_DIR / "emoji_panel_02.jpg")
    print(f"  生成: {p2}")
    p3 = create_emoji_panel_3(SAMPLES_DIR / "emoji_panel_03.jpg")
    print(f"  生成: {p3}")

    # パターンA: チビキャラ
    print("\n--- パターンA: チビキャラ＋国旗バッジ ---")
    c1 = create_chibi_panel_1(SAMPLES_DIR / "chibi_panel_01.jpg")
    print(f"  生成: {c1}")
    c2 = create_chibi_panel_2(SAMPLES_DIR / "chibi_panel_02.jpg")
    print(f"  生成: {c2}")
    c3 = create_chibi_panel_3(SAMPLES_DIR / "chibi_panel_03.jpg")
    print(f"  生成: {c3}")

    # Shortsフレーム合成サンプル（各パターン1枚ずつ）
    print("\n--- Shortsフレーム合成 ---")
    wrap_in_shorts_frame(
        SAMPLES_DIR / "emoji_panel_01.jpg",
        SAMPLES_DIR / "shorts_frame_emoji.jpg",
        "📉スタグフレーションとは？📈",
        "物価が上がり続けるのに、景気は停滞する。この最悪の組み合わせです。"
    )
    print(f"  生成: {SAMPLES_DIR / 'shorts_frame_emoji.jpg'}")

    wrap_in_shorts_frame(
        SAMPLES_DIR / "chibi_panel_01.jpg",
        SAMPLES_DIR / "shorts_frame_chibi.jpg",
        "スタグフレーションとは？",
        "物価が上がり続けるのに、景気は停滞する。この最悪の組み合わせです。"
    )
    print(f"  生成: {SAMPLES_DIR / 'shorts_frame_chibi.jpg'}")

    print("\n✅ 全サンプル生成完了！")
    print(f"出力先: {SAMPLES_DIR}")
    print("\n比較してください:")
    print("  絵文字パターン: emoji_panel_01~03.jpg + shorts_frame_emoji.jpg")
    print("  チビキャラパターン: chibi_panel_01~03.jpg + shorts_frame_chibi.jpg")
