#!/usr/bin/env python3
"""
Gemini API 画像生成スクリプト（エイミー先生の経済学）

16:9横型のアニメ風イラストを生成する。
Shorts枠内の16:9コンテンツ用素材として使用。

使い方:
  python3 scripts/gemini_image_gen.py --prompt "プロンプト" --output output.png
  python3 scripts/gemini_image_gen.py --test  # テスト生成
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types

PROJECT_ROOT = Path(__file__).parent.parent

# Vertex AI (ADC認証 — gcloud auth application-default login で設定済み)
GCP_PROJECT = os.getenv("GCP_PROJECT", "nihon-kore-iinkai")
GCP_LOCATION = os.getenv("GCP_LOCATION", "us-central1")
client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)

# 画像生成対応モデル
MODELS = {
    "flash": "gemini-2.0-flash-exp-image-generation",
    "flash25": "gemini-2.5-flash-image",
    "pro": "gemini-3-pro-image-preview",
    "flash31": "gemini-3.1-flash-image-preview",
}
DEFAULT_MODEL = "flash25"

# デフォルトリファレンス画像（1枚のみ）
# reference: エイミー先生＋少年＋フェルミ絵柄＋絵文字モブの総合リファレンス（16:9）
DEFAULT_REFERENCES = {
    "reference": str(PROJECT_ROOT / "assets/image_library/characters/references/reference.png"),
}


def generate_image(prompt, output_path, aspect="16:9", model_key=None, reference_images=None, max_retries=2):
    """Gemini APIで画像生成

    Args:
        reference_images: list of file paths to reference images
    """
    model_key = model_key or DEFAULT_MODEL
    model = MODELS.get(model_key, model_key)

    # Preflight: 参照画像がある場合、プロンプトに参照指示を自動追加
    if reference_images:
        if "reference image" not in prompt.lower() and "provided image" not in prompt.lower():
            prompt = ("The provided reference image shows the exact character designs and art style to use. "
                      "Match the teacher (silver hair, blue eyes, red outfit), the boy (teal hair, round glasses, hoodie, same height as teacher), "
                      "and the emoji-faced mob characters (yellow circle emoji faces on chibi bodies) precisely. "
                      "Do NOT introduce new character designs.\n\n") + prompt
    # Preflight: テキスト混入防止を自動追加
    if "do not include any text" not in prompt.lower() and "no text" not in prompt.lower():
        prompt += "\n\nDo not include any text, writing, letters, numbers, or speech bubbles in the image."

    full_prompt = f"""Generate an image with the following description.
Aspect ratio: {aspect}

{prompt}

Important: Generate ONLY an image, no text response."""

    # Build parts: reference images first, then text prompt
    contents = []
    if reference_images:
        for ref_path in reference_images:
            ref_path = Path(ref_path)
            if not ref_path.exists():
                print(f"  Warning: reference image not found: {ref_path}")
                continue
            img_bytes = ref_path.read_bytes()
            suffix = ref_path.suffix.lower()
            mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type=mime))
            print(f"  Reference image: {ref_path.name} ({len(img_bytes) / 1024:.0f}KB)")
    contents.append(full_prompt)

    print(f"Generating image...")
    print(f"  Model: {model}")
    print(f"  Aspect: {aspect}")
    print(f"  Prompt: {prompt[:100]}...")

    try:
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )
    except Exception as e:
        print(f"API Error: {e}")
        if max_retries > 0:
            print(f"  Retrying... ({max_retries} retries left)")
            time.sleep(5)
            return generate_image(prompt, output_path, aspect, model_key, reference_images, max_retries - 1)
        return False

    # レスポンスから画像を抽出
    if not response.candidates:
        print(f"No candidates in response")
        return False

    parts = response.candidates[0].content.parts

    image_saved = False
    for part in parts:
        if part.inline_data:
            mime = part.inline_data.mime_type or "image/png"
            img_bytes = part.inline_data.data

            ext = ".png" if "png" in mime else ".jpg"
            out = Path(output_path)
            if out.suffix not in ('.png', '.jpg', '.jpeg'):
                out = out.with_suffix(ext)

            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(img_bytes)
            print(f"  Saved: {out} ({len(img_bytes) / 1024:.0f}KB)")
            image_saved = True
        elif part.text:
            print(f"  Text response: {part.text[:200]}")

    if not image_saved:
        print("No image in response.")
        if max_retries > 0:
            print(f"  Retrying... ({max_retries} retries left)")
            time.sleep(3)
            return generate_image(prompt, output_path, aspect, model_key, reference_images, max_retries - 1)
        return False

    # 生成後ファイル存在確認
    out = Path(output_path)
    if not out.exists() and not out.with_suffix('.png').exists() and not out.with_suffix('.jpg').exists():
        print(f"  ERROR: File not found after generation: {output_path}")
        if max_retries > 0:
            print(f"  Retrying... ({max_retries} retries left)")
            time.sleep(3)
            return generate_image(prompt, output_path, aspect, model_key, reference_images, max_retries - 1)
        return False

    return True


def generate_from_scenes(scenes_json_path, model_key=None):
    """scenes.jsonからプロンプトのあるシーンを一括生成（リトライ付き）"""
    scenes_path = Path(scenes_json_path)
    with open(scenes_path, "r", encoding="utf-8") as f:
        scenes_data = json.load(f)

    meta = scenes_data.get("meta", {})
    ref_map = meta.get("references", {})

    scenes = scenes_data.get("scenes", [])

    # Preflight: メインキャラ登場比率チェック（33-40%ルール）
    gemini_scenes = [s for s in scenes if s.get("asset_type") == "gemini" and s.get("prompt")]
    if gemini_scenes:
        missing_field = [s["id"] for s in gemini_scenes if "has_main_character" not in s]
        if missing_field:
            print(f"\n  PREFLIGHT ERROR: has_main_character フィールドが未設定のシーンがあります:")
            for sid in missing_field:
                print(f"    - {sid}")
            print(f"  scenes.jsonの各Geminiシーンに has_main_character: true/false を追加してください。")
            print(f"  ルール: メインキャラ（エイミー先生・少年）の登場は全Geminiシーンの33-40%に抑える")
            return False

        main_char_count = sum(1 for s in gemini_scenes if s.get("has_main_character"))
        total = len(gemini_scenes)
        ratio = main_char_count / total if total > 0 else 0
        print(f"\n  Preflight: メインキャラ登場比率 {main_char_count}/{total} ({ratio:.0%})")
        if ratio > 0.45:
            print(f"  PREFLIGHT ERROR: メインキャラ登場比率が{ratio:.0%}で上限40%を超えています。")
            print(f"  モブ（絵文字顔）中心のシーンを増やしてください。")
            return False
        print(f"  Preflight: メインキャラ比率OK ({ratio:.0%} ≤ 40%)")

    results = {"ok": [], "failed": [], "skipped": []}

    for scene in scenes:
        sid = scene["id"]
        prompt = scene.get("prompt")
        asset = scene.get("asset", "")
        reuse = scene.get("reuse", False)

        # スキップ条件: reuse=True、プロンプトなし、既に生成済み
        if reuse or not prompt:
            results["skipped"].append(sid)
            print(f"  SKIP {sid} (reuse={reuse}, prompt={'yes' if prompt else 'no'})")
            continue

        output_path = PROJECT_ROOT / asset
        if output_path.exists():
            results["skipped"].append(sid)
            print(f"  SKIP {sid} (already exists: {asset})")
            continue

        # 参照画像の解決
        ref_images = None
        ref_key = scene.get("ref_image")
        if ref_key and ref_key in ref_map:
            ref_path = PROJECT_ROOT / ref_map[ref_key]
            if ref_path.exists():
                ref_images = [str(ref_path)]
            else:
                print(f"  WARNING: reference image not found: {ref_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"\n--- {sid} ---")
        success = generate_image(prompt, str(output_path), "16:9", model_key, ref_images, max_retries=2)

        if success:
            results["ok"].append(sid)
        else:
            results["failed"].append(sid)

        # API rate limit対策
        time.sleep(2)

    # サマリー報告
    print(f"\n{'='*50}")
    print(f"画像生成サマリー:")
    print(f"  OK: {len(results['ok'])} ({', '.join(results['ok'])})")
    print(f"  FAILED: {len(results['failed'])} ({', '.join(results['failed'])})")
    print(f"  SKIPPED: {len(results['skipped'])} ({', '.join(results['skipped'])})")
    if results["failed"]:
        print(f"\n  失敗シーンがあります。手動で再生成してください:")
        for sid in results["failed"]:
            scene = next(s for s in scenes if s["id"] == sid)
            print(f"    {sid}: {scene.get('asset', 'unknown')}")
    print(f"{'='*50}")

    return len(results["failed"]) == 0


def main():
    parser = argparse.ArgumentParser(description="Gemini画像生成（経済学版）")
    parser.add_argument("--prompt", "-p", type=str, help="画像プロンプト")
    parser.add_argument("--output", "-o", type=str, default="output/test_gen.png")
    parser.add_argument("--aspect", type=str, default="16:9", help="アスペクト比（デフォルト: 16:9）")
    parser.add_argument("--model", "-m", type=str, default=None,
                        choices=list(MODELS.keys()), help="モデル選択")
    parser.add_argument("--ref", "-r", type=str, nargs="+", help="参照画像パス（複数可）")
    parser.add_argument("--ref-key", type=str, nargs="+",
                        choices=list(DEFAULT_REFERENCES.keys()),
                        help="デフォルトリファレンスキー（reference）")
    parser.add_argument("--scenes", "-s", type=str, help="scenes.jsonパス（一括生成）")
    parser.add_argument("--test", action="store_true", help="テスト生成")
    args = parser.parse_args()

    # リファレンス画像の解決
    ref_images = args.ref or []
    if args.ref_key:
        for key in args.ref_key:
            path = DEFAULT_REFERENCES.get(key)
            if path and Path(path).exists():
                ref_images.append(path)
            else:
                print(f"  Warning: default reference '{key}' not found: {path}")

    if args.scenes:
        success = generate_from_scenes(args.scenes, args.model)
        sys.exit(0 if success else 1)
    elif args.test:
        prompt = """Cute anime style illustration, horizontal composition (16:9 landscape).
A chibi anime girl teacher with long brown hair in a business suit,
standing in front of a blackboard with economic charts and graphs.
She has big expressive eyes and is pointing at a rising stock chart.
Bright, clean art style with soft colors. No text in the image.
Japanese anime art style, high quality illustration."""
        output = str(PROJECT_ROOT / "output/test_econ_16x9.png")
        generate_image(prompt, output, "16:9", args.model, ref_images or None)
    elif args.prompt:
        generate_image(args.prompt, args.output, args.aspect, args.model, ref_images or None)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
