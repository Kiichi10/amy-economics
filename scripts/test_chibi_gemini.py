#!/usr/bin/env python3
"""
Gemini画像生成テスト — ちびキャラスタイル
エイミー先生＋少年は固有顔、モブは絵文字顔
"""

import requests
import base64
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY not found")
    sys.exit(1)

MODEL = "gemini-2.5-flash-image"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

OUTPUT_DIR = PROJECT_ROOT / "samples" / "chibi_gemini"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# エイミー先生と少年の共通デザイン指示
AMY_DESIGN = """Amy-sensei (female teacher): A cute chibi/2-head-tall anime character with proper drawn face (NOT emoji).
Blonde hair in a bob cut, bright blue eyes, wearing a red blazer over white blouse.
Confident, warm smile. She is the main character and must look consistent."""

BOY_DESIGN = """Boy student: A cute chibi/2-head-tall anime character with proper drawn face (NOT emoji).
Short black messy hair, brown eyes, wearing a blue hoodie.
Curious, energetic expression. He is the secondary main character."""

MOB_EMOJI_RULE = """All other background/mob characters must have YELLOW CIRCLE EMOJI FACES instead of normal drawn faces.
Their bodies are chibi anime style but their faces are simple yellow emoji circles with emoji-like expressions."""


def generate_image(prompt, output_path, aspect="16:9"):
    full_prompt = f"""Generate an image with the following description.
Aspect ratio: {aspect}

{prompt}

Important: Generate ONLY an image, no text response.
Do not include any text, writing, letters, numbers, or speech bubbles in the image."""

    payload = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
        }
    }

    print(f"  Generating: {output_path.name}...")
    try:
        resp = requests.post(API_URL, json=payload, timeout=120)
        if resp.status_code != 200:
            print(f"  ERROR: API returned {resp.status_code}")
            print(f"  {resp.text[:300]}")
            return False

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            print("  ERROR: No candidates")
            return False

        for part in candidates[0].get("content", {}).get("parts", []):
            if "inlineData" in part:
                img_data = base64.b64decode(part["inlineData"]["data"])
                mime = part["inlineData"].get("mimeType", "image/png")
                ext = ".png" if "png" in mime else ".jpg"
                final_path = output_path.with_suffix(ext)
                final_path.write_bytes(img_data)
                print(f"  OK: {final_path}")
                return True

        print("  ERROR: No image data")
        for part in candidates[0].get("content", {}).get("parts", []):
            if "text" in part:
                print(f"  Text: {part['text'][:200]}")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("ちびキャラスタイル テスト（固有顔メイン + 絵文字顔モブ）")
    print("=" * 60)

    # === テスト1: エイミー先生が教室で解説 + 絵文字顔モブ生徒 ===
    print("\n--- テスト1: 教室シーン（エイミー先生 + 絵文字顔モブ） ---")
    generate_image(
        f"""Chibi anime style (2-3 head tall proportions) economic education illustration.
Scene: A bright, modern classroom.

Main characters (with PROPER DRAWN ANIME FACES):
{AMY_DESIGN}
She is standing at the front, pointing at a whiteboard with economic charts.

{BOY_DESIGN}
He is sitting at a desk in the front row, looking up at Amy-sensei with curiosity.

Background mob students (3-4 characters sitting at desks):
{MOB_EMOJI_RULE}
Each mob student has a different emoji expression (confused, sleepy, interested).

Style: Cute chibi anime, like Japanese economic explainer YouTube channels.
Clean lines, bright colors, warm classroom lighting.
Similar to 'Sukkiri Economics' YouTube channel style.""",
        OUTPUT_DIR / "test1_classroom"
    )
    time.sleep(5)

    # === テスト2: スタグフレーション解説（エイミー先生＋少年 + 国旗絵文字モブ） ===
    print("\n--- テスト2: 経済解説シーン（メインキャラ + 国旗モブ） ---")
    generate_image(
        f"""Chibi anime style (2-3 head tall proportions) economic news illustration.
Scene: Split composition showing economic crisis.

Left side - Japanese economy troubles:
{AMY_DESIGN}
She is explaining with a serious but caring expression, gesturing toward economic indicators.

{BOY_DESIGN}
He looks worried/shocked, standing next to Amy-sensei.

Right side - International factors:
Two mob chibi characters representing countries:
{MOB_EMOJI_RULE}
- One mob character with a 😤 emoji face, wearing dark suit, with a small Saudi Arabia flag nearby
- One mob character with a 😏 emoji face, wearing suit, with a small USA flag nearby

Center: Red upward arrows (oil prices) and blue downward arrows (yen value).
Background: Dark navy blue, infographic style.
Style: Cute but informative chibi anime, like Japanese economic YouTube explainer videos.""",
        OUTPUT_DIR / "test2_stagflation"
    )
    time.sleep(5)

    # === テスト3: 日銀ジレンマ（エイミー先生が解説、絵文字顔の日銀総裁） ===
    print("\n--- テスト3: 日銀ジレンマ（エイミー先生 + 絵文字顔日銀総裁） ---")
    generate_image(
        f"""Chibi anime style (2-3 head tall proportions) illustration about Bank of Japan's dilemma.
Scene: A dramatic crossroads/fork in the road scene.

Center:
A mob chibi character representing the Bank of Japan governor:
{MOB_EMOJI_RULE}
This character has a 😰 sweating/worried emoji face, wearing a formal dark suit. Standing at a fork in the road.

Left path (labeled with upward interest rate icon):
Shows factories closing (dark, smoke) — negative consequence.

Right path (labeled with stable/flat interest rate icon):
Shows prices/yen falling — negative consequence.

In the foreground, watching the scene:
{AMY_DESIGN}
She has a thoughtful, analytical expression.

{BOY_DESIGN}
He looks confused and worried.

Style: Cute chibi anime with dramatic lighting at the crossroads.
Dark background with spotlight effect. Like Japanese economic YouTube channels.""",
        OUTPUT_DIR / "test3_boj_dilemma"
    )
    time.sleep(5)

    # === テスト4: エイミー先生と少年のキャラクター立ち絵 ===
    print("\n--- テスト4: キャラクターリファレンス（立ち絵） ---")
    generate_image(
        f"""Character reference sheet, chibi anime style (2-3 head tall proportions).
White/light gray clean background.

Two characters standing side by side:

Left character:
{AMY_DESIGN}
Full body view, standing confidently with one hand on hip.

Right character:
{BOY_DESIGN}
Full body view, standing with a curious pose, hands in hoodie pockets.

Style: Clean character design sheet. No background clutter.
Bright, appealing colors. Professional anime character design.
These are the main recurring characters for an economics YouTube channel.""",
        OUTPUT_DIR / "test4_character_ref"
    )

    print("\n✅ テスト完了！")
    print(f"出力先: {OUTPUT_DIR}")
