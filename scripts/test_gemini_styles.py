#!/usr/bin/env python3
"""
Gemini画像生成テスト — 絵文字顔キャラクターのスタイル検証
アプローチA: Geminiに絵文字顔キャラを直接描かせる
アプローチB: 顔なしキャラを生成 → Pillow後処理で絵文字オーバーレイ
"""

import requests
import base64
import json
import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY not found in .env")
    sys.exit(1)

MODEL = "gemini-2.5-flash-image"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

OUTPUT_DIR = PROJECT_ROOT / "samples" / "gemini_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def generate_image(prompt, output_path, aspect="16:9"):
    """Gemini API で画像を生成"""
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
            print(f"  {resp.text[:500]}")
            return False

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            print("  ERROR: No candidates in response")
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

        print("  ERROR: No image data in response")
        # Print text parts for debugging
        for part in candidates[0].get("content", {}).get("parts", []):
            if "text" in part:
                print(f"  Text response: {part['text'][:200]}")
        return False

    except Exception as e:
        print(f"  ERROR: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Gemini 絵文字顔キャラクター スタイルテスト")
    print("=" * 60)

    # === テスト1: 絵文字顔キャラを直接描かせる ===
    print("\n--- テスト1: 絵文字顔を直接描画 ---")

    generate_image(
        """Japanese anime style economic explainer illustration.
A classroom or news studio scene with two characters:
1. A female teacher character (blonde hair, red blazer, professional) - her face is replaced by a large yellow circle emoji face with a confident smile expression, like the 😊 emoji
2. A young boy student character (casual clothes) - his face is replaced by a large yellow circle emoji face with a surprised/confused expression, like the 😲 emoji

The characters have emoji-style yellow circle faces instead of normal anime faces. Their bodies are anime-style but faces are simple emoji circles.

Background: A modern classroom with a whiteboard showing economic graphs (stock charts going down, oil barrel icon).
Style: Clean, colorful, anime illustration. Warm lighting.""",
        OUTPUT_DIR / "test1_emoji_face_classroom"
    )
    time.sleep(3)

    # === テスト2: スタグフレーション解説シーン ===
    print("\n--- テスト2: 経済危機シーン（絵文字顔キャラ群） ---")

    generate_image(
        """Japanese anime style economic illustration about stagflation crisis.
Scene: A Japanese city street with rising price tags on shops and a factory with smoke stacks in the background.

Multiple characters walking on the street, all with EMOJI-STYLE YELLOW CIRCLE FACES instead of normal faces:
- A worried housewife carrying expensive groceries (her face is a 😰 worried emoji circle)
- A stressed businessman (his face is a 😫 exhausted emoji circle)
- A confused student (his face is a 🤔 thinking emoji circle)

The characters have normal anime bodies but their faces are replaced with large yellow circle emoji expressions.
Visual elements: Red upward arrows on price tags, blue downward arrows on a GDP graph.
Style: Bright, clean anime illustration. Slightly satirical tone.""",
        OUTPUT_DIR / "test2_stagflation_street"
    )
    time.sleep(3)

    # === テスト3: 国旗キャラの対立シーン ===
    print("\n--- テスト3: 国際対立シーン（絵文字顔＋国旗） ---")

    generate_image(
        """Japanese anime style geopolitical illustration.
Scene: Two sides facing each other across a table in a diplomatic meeting room.

Left side: A character wearing a suit with a Japanese flag pin. The character's face is a large yellow emoji circle with a 😤 determined expression. Behind them is a Japanese flag.

Right side: A character wearing a suit with an American flag pin. The character's face is a large yellow emoji circle with a 😎 cool/confident expression. Behind them is an American flag.

Between them on the table: documents, a car model, and stacks of money.
The characters have normal anime-style bodies but EMOJI YELLOW CIRCLE FACES.
Style: Clean anime illustration, diplomatic tension atmosphere, warm indoor lighting.""",
        OUTPUT_DIR / "test3_diplomacy_emoji"
    )
    time.sleep(3)

    # === テスト4: スッキリ経済学スタイル（棒人間風 + 絵文字顔） ===
    print("\n--- テスト4: 棒人間＋絵文字顔ハイブリッド ---")

    generate_image(
        """Simple illustration in the style of Japanese economic explainer videos.
Clean, minimal background with dark blue/navy color.

Two simple stick-figure-like characters with oversized heads:
1. A teacher character with a yellow emoji smiley face (😊), wearing a simple red outfit
2. A student character with a yellow emoji surprised face (😮), wearing a simple blue outfit

Between them: A simple diagram showing "oil barrel" on the left with a red UP arrow, and "yen symbol ¥" on the right with a blue DOWN arrow.

Style: Very clean, flat design, minimal details, like an infographic or economic explainer video.
Dark navy background, bright colored characters and icons.""",
        OUTPUT_DIR / "test4_simple_explainer"
    )

    print("\n✅ テスト完了！")
    print(f"出力先: {OUTPUT_DIR}")
