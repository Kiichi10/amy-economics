#!/usr/bin/env python3
"""
A1画像にPillowで実際の絵文字をオーバーレイするテスト
Geminiが描いた絵文字風の顔を、実際のApple Emoji で上書きする
"""

from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji
from pathlib import Path

OUTPUT_DIR = Path("/Users/kiichi/Documents/VS Code/エイミー先生の経済学/samples/fermi_style")
A1_PATH = OUTPUT_DIR / "A1_classroom.png"

def get_font(size):
    return ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", size)

def overlay_emoji(input_path, output_path, emoji_specs):
    """
    画像上の指定位置に実際の絵文字をオーバーレイ
    emoji_specs: [(center_x, center_y, radius, emoji_char), ...]
    """
    img = Image.open(input_path).convert("RGBA")
    w, h = img.size
    print(f"Image size: {w}x{h}")

    # 絵文字レイヤー
    emoji_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(emoji_layer)

    for cx, cy, r, emoji_char in emoji_specs:
        # 白い円で元の顔を隠す
        draw.ellipse(
            [(cx - r, cy - r), (cx + r, cy + r)],
            fill=(255, 255, 255, 255)
        )

    # 絵文字をPilmojiで描画
    with Pilmoji(emoji_layer) as pmj:
        for cx, cy, r, emoji_char in emoji_specs:
            emoji_size = int(r * 1.8)
            font = get_font(emoji_size)
            # 絵文字を中央に配置
            pmj.text(
                (cx - emoji_size // 2 + 2, cy - emoji_size // 2 + 2),
                emoji_char,
                font=font
            )

    # 合成
    result = Image.alpha_composite(img, emoji_layer)
    result.convert("RGB").save(output_path, quality=95)
    print(f"OK: {output_path}")


if __name__ == "__main__":
    img = Image.open(A1_PATH)
    w, h = img.size
    print(f"A1 image size: {w}x{h}")

    # A1の画像を見て、モブ生徒の顔位置を特定
    # 画像を確認: 後ろの机に4人の絵文字顔モブがいる
    # 位置はピクセル単位で指定（画像サイズに依存）

    # まず画像サイズに基づいて相対位置で指定
    # A1は9:16比率で生成されたようなので、モブの位置を推定
    # 後列左から: 4人の絵文字顔モブ

    # 複数パターンを試す
    # パターン1: 大きめの絵文字
    specs_large = [
        (int(w * 0.18), int(h * 0.28), int(w * 0.07), "😴"),  # 左奥
        (int(w * 0.38), int(h * 0.26), int(w * 0.07), "🤔"),  # 左中
        (int(w * 0.62), int(h * 0.26), int(w * 0.07), "😰"),  # 右中
        (int(w * 0.82), int(h * 0.28), int(w * 0.07), "😲"),  # 右奥
    ]

    overlay_emoji(
        A1_PATH,
        OUTPUT_DIR / "A1_with_real_emoji_v1.jpg",
        specs_large
    )

    # パターン2: 位置微調整版（もう少し上）
    specs_v2 = [
        (int(w * 0.18), int(h * 0.25), int(w * 0.08), "😴"),
        (int(w * 0.38), int(h * 0.23), int(w * 0.08), "🤔"),
        (int(w * 0.62), int(h * 0.23), int(w * 0.08), "😰"),
        (int(w * 0.82), int(h * 0.25), int(w * 0.08), "😲"),
    ]

    overlay_emoji(
        A1_PATH,
        OUTPUT_DIR / "A1_with_real_emoji_v2.jpg",
        specs_v2
    )

    print("\n✅ 完了！A1オリジナルとオーバーレイ版を比較してください")
