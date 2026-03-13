#!/usr/bin/env python3
"""
Gemini画像生成テスト — フェルミ研究所スタイル
アプローチA: Geminiに絵文字顔モブを直接描かせる（リファレンス画像付き）
アプローチB: Geminiで顔なしモブ生成 → Pillow後処理で実際の絵文字オーバーレイ
"""

import requests
import base64
import os
import sys
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pilmoji import Pilmoji
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY not found")
    sys.exit(1)

MODEL = "gemini-2.5-flash-image"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

OUTPUT_DIR = PROJECT_ROOT / "samples" / "fermi_style"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# リファレンス画像パス
AMY_REF = Path("/Users/kiichi/Documents/VS Code/エイミー先生の時事ニュース/assets/image_library/characters/amy_sensei/reference.png")
SHONEN_REF = Path("/Users/kiichi/Documents/VS Code/日本はこれで委員会/assets/characters/shonen.jpg")
FERMI_CAMERON_REF = Path("/Users/kiichi/Downloads/フェルミ自動_Nanobanana Pro/assets/chars/cameron/default.png")
FERMI_TAKERU_REF = Path("/Users/kiichi/Downloads/フェルミ自動_Nanobanana Pro/assets/chars/takeru/default.png")

# エイミー先生の正確な特徴
AMY_DESC = """Amy-sensei (main female character):
- Silver/white long straight hair flowing down past shoulders
- Bright blue eyes
- Wearing a red/maroon professional outfit (blazer or dress)
- Confident, warm expression
- She is NOT blonde. Her hair is SILVER/WHITE."""

# 少年の正確な特徴（名前はタケルではない）
SHONEN_DESC = """Boy student (main male character):
- Dark teal/green messy hair with an ahoge (hair antenna)
- Round glasses
- Green/teal eyes
- Wearing a white hoodie with a cute green dinosaur print on the front
- Khaki cargo pants
- White sneakers
- Curious, slightly nerdy appearance"""

# フェルミスタイル指示
FERMI_STYLE = """Art style: Japanese YouTube explainer channel chibi style (like Fermi Lab/フェルミ研究所).
- 2-3 head tall chibi proportions
- Clean, soft line art
- Soft cel shading with gentle shadows
- Light/white/light gray clean background
- Warm, friendly, approachable look
- Simple but expressive character designs
- NOT realistic, NOT detailed anime — SIMPLE and CUTE chibi style"""


def load_image_as_base64(path):
    """画像をbase64エンコード"""
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return data, mime


def generate_image_with_refs(prompt, output_path, ref_images=None, aspect="16:9"):
    """リファレンス画像付きでGemini画像生成"""
    parts = []

    # リファレンス画像を追加
    if ref_images:
        ref_instruction = "Use these reference images as character design guides. Match their appearance precisely in the Fermi/chibi art style:\n"
        for label, ref_path in ref_images:
            if ref_path.exists():
                data, mime = load_image_as_base64(ref_path)
                ref_instruction += f"- {label}\n"
                parts.append({"inlineData": {"mimeType": mime, "data": data}})
        parts.insert(0, {"text": ref_instruction})

    # メインプロンプト
    full_prompt = f"""Generate an image with the following description.
Aspect ratio: {aspect}

{prompt}

Important: Generate ONLY an image, no text response.
Do not include any text, writing, letters, numbers, or speech bubbles in the image."""

    parts.append({"text": full_prompt})

    payload = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        }
    }

    print(f"  Generating: {output_path.name}...")
    try:
        resp = requests.post(API_URL, json=payload, timeout=180)
        if resp.status_code != 200:
            print(f"  ERROR: API returned {resp.status_code}")
            error_text = resp.text[:500]
            print(f"  {error_text}")
            return None

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            print("  ERROR: No candidates")
            return None

        for part in candidates[0].get("content", {}).get("parts", []):
            if "inlineData" in part:
                img_data = base64.b64decode(part["inlineData"]["data"])
                mime = part["inlineData"].get("mimeType", "image/png")
                ext = ".png" if "png" in mime else ".jpg"
                final_path = output_path.with_suffix(ext)
                final_path.write_bytes(img_data)
                print(f"  OK: {final_path}")
                return final_path

        print("  ERROR: No image data in response")
        for part in candidates[0].get("content", {}).get("parts", []):
            if "text" in part:
                print(f"  Text: {part['text'][:300]}")
        return None
    except Exception as e:
        print(f"  ERROR: {e}")
        return None


def overlay_emoji_on_faces(input_path, output_path, emoji_positions):
    """
    アプローチB: 生成画像の顔部分に実際の絵文字をオーバーレイ
    emoji_positions: [(x, y, size, emoji_char), ...]
    """
    img = Image.open(input_path).convert("RGBA")

    # 絵文字レイヤーを作成
    emoji_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))

    def get_font(size):
        return ImageFont.truetype("/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", size)

    with Pilmoji(emoji_layer) as pmj:
        for x, y, size, emoji_char in emoji_positions:
            # 白い円の背景（絵文字の下地）
            draw = ImageDraw.Draw(emoji_layer)
            r = size // 2 + 4
            draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=(255, 255, 255, 230))
            # 絵文字を配置
            pmj.text((x - size // 2 + 2, y - size // 2 + 2), emoji_char,
                     font=get_font(size))

    # 合成
    result = Image.alpha_composite(img, emoji_layer)
    result = result.convert("RGB")
    result.save(output_path, quality=95)
    print(f"  Emoji overlay: {output_path}")
    return output_path


if __name__ == "__main__":
    print("=" * 60)
    print("フェルミスタイル テスト（リファレンス画像付き）")
    print("=" * 60)

    # リファレンス画像セット
    char_refs = [
        ("Amy-sensei (silver hair, blue eyes, red outfit)", AMY_REF),
        ("Boy student (teal hair, glasses, dinosaur hoodie)", SHONEN_REF),
        ("Fermi-style chibi example 1 (target art style)", FERMI_CAMERON_REF),
        ("Fermi-style chibi example 2 (target art style)", FERMI_TAKERU_REF),
    ]

    # === アプローチA-1: エイミー先生＋少年の解説シーン（絵文字顔モブ） ===
    print("\n--- A-1: 教室解説シーン（固有顔メイン + 絵文字顔モブ） ---")
    result_a1 = generate_image_with_refs(
        f"""{FERMI_STYLE}

Scene: A bright classroom/studio setting.

Main characters (draw with PROPER ANIME FACES matching their reference images):
{AMY_DESC}
She is standing and pointing/gesturing, explaining something with enthusiasm.

{SHONEN_DESC}
He is sitting/standing next to her, looking curious and interested.

Background mob characters (3 students at desks):
These mob characters must have ACTUAL YELLOW EMOJI CIRCLE FACES (like real smartphone emoji 😰😲🤔) instead of drawn anime faces. Their bodies are chibi style but heads are yellow emoji circles.

Background: Clean, light classroom. A whiteboard behind them with simple economic chart shapes.""",
        OUTPUT_DIR / "A1_classroom",
        ref_images=char_refs
    )
    time.sleep(8)

    # === アプローチA-2: スタグフレーション（国旗絵文字モブ） ===
    print("\n--- A-2: 経済対立シーン（固有顔メイン + 国旗絵文字モブ） ---")
    result_a2 = generate_image_with_refs(
        f"""{FERMI_STYLE}

Scene: Economic crisis illustration with split composition.

Left side - Amy-sensei and the boy student:
{AMY_DESC}
She looks serious, explaining with her hand raised.
{SHONEN_DESC}
He looks shocked/worried.

Right side - International mob characters:
Two chibi-body characters representing foreign countries.
IMPORTANT: These two characters have REAL YELLOW EMOJI FACES (like actual smartphone emoji) instead of drawn faces:
- Character 1: body in dark suit, face is a 😤 emoji yellow circle. Small oil barrel icon nearby.
- Character 2: body in business suit, face is a 😏 emoji yellow circle. Small USA flag pin.

Center visual elements: Red arrows going UP (oil prices), blue arrows going DOWN (yen value).
Background: Light/white, clean infographic style.""",
        OUTPUT_DIR / "A2_stagflation",
        ref_images=char_refs
    )
    time.sleep(8)

    # === アプローチB-1: 顔なしモブ生成（後処理用） ===
    print("\n--- B-1: 顔なしモブ生成（Pillow後処理用） ---")
    result_b1 = generate_image_with_refs(
        f"""{FERMI_STYLE}

Scene: Economic news illustration.

Left side:
{AMY_DESC}
She is explaining something, pointing to the right side of the image.
{SHONEN_DESC}
He stands next to her looking surprised.

Right side - 3 mob chibi characters in a row:
These mob characters have BLANK WHITE CIRCLES for faces (no facial features at all - just smooth white circles where heads should be). Their bodies are normal chibi style with suits.
- Character 1: dark suit, blank white circle head, small Saudi Arabia flag nearby
- Character 2: dark suit, blank white circle head, small Russia flag nearby
- Character 3: business casual, blank white circle head, small USA flag nearby

Their heads are PERFECTLY ROUND WHITE CIRCLES with no eyes, no mouth, nothing drawn on them.

Background: Light/white clean setting. Simple economic chart in background.""",
        OUTPUT_DIR / "B1_faceless_mobs",
        ref_images=char_refs
    )

    # === アプローチB後処理: 絵文字オーバーレイ ===
    if result_b1 and result_b1.exists():
        print("\n--- B-1 後処理: 絵文字オーバーレイ ---")
        # 注: 顔の位置は生成結果に依存するため、手動で調整が必要
        # ここでは右半分の3キャラの推定位置で試行
        img = Image.open(result_b1)
        w, h = img.size
        # 右側3キャラの推定顔位置（生成結果に応じて調整）
        emoji_positions = [
            (int(w * 0.55), int(h * 0.35), 60, "😤"),
            (int(w * 0.72), int(h * 0.35), 60, "😠"),
            (int(w * 0.88), int(h * 0.35), 60, "😏"),
        ]
        overlay_emoji_on_faces(
            result_b1,
            OUTPUT_DIR / "B1_with_emoji_overlay.jpg",
            emoji_positions
        )

    print("\n✅ テスト完了！")
    print(f"出力先: {OUTPUT_DIR}")
    print("\n比較してください:")
    print("  A1: Geminiが直接描いた絵文字顔モブ（教室）")
    print("  A2: Geminiが直接描いた絵文字顔モブ（経済対立）")
    print("  B1: 顔なしモブ → 実際の絵文字オーバーレイ")
