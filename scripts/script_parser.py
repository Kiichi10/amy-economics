#!/usr/bin/env python3
"""
台本パーサー: 対話形式の台本テキストを構造化データに変換する。

入力フォーマット（フェルミプロンプト出力形式）:
    Amy, セリフ本文
    Shonen, セリフ本文

出力: sections配列（各セクションにspeaker, text, voicevox_speaker_id等を含む）
"""

import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional


def load_config(config_path: Optional[str] = None) -> Dict:
    """config.jsonを読み込み、キャラクター名マッピングを構築する。"""
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.json"
    else:
        config_path = Path(config_path)

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_name_map(config: Dict) -> Dict[str, str]:
    """キャラクター名（エイリアス含む）→ キャラクターキーのマッピングを構築。"""
    name_map = {}
    for char_key, char_data in config["characters"].items():
        # キーそのもの
        name_map[char_key.lower()] = char_key
        # display_name
        name_map[char_data["display_name"].lower()] = char_key
        # エイリアス
        for alias in char_data.get("aliases", []):
            name_map[alias.lower()] = char_key

    return name_map


def parse_script(script_text: str, config: Optional[Dict] = None) -> Dict:
    """
    対話形式の台本テキストを構造化データに変換する。

    Args:
        script_text: "キャラ名, セリフ" 形式の台本テキスト
        config: config.json の内容（Noneの場合は自動読み込み）

    Returns:
        {"sections": [...]} 形式の構造化データ
    """
    if config is None:
        config = load_config()

    name_map = build_name_map(config)
    characters = config["characters"]

    # ナレーションモード判定: 台本に登場する話者が1人なら行ごとに独立セクション化
    # config.jsonのキャラ数ではなく、台本内の実際の話者数で判定
    speakers_in_script = set()
    for line in script_text.strip().split("\n"):
        line = line.strip()
        if "," in line:
            speaker_raw = line.split(",", 1)[0].strip()
            speakers_in_script.add(speaker_raw.lower())
    split_per_line = len(speakers_in_script) <= 1

    sections = []
    current_speaker = None
    current_lines = []

    for line in script_text.strip().split("\n"):
        line = line.strip()

        # 空行はスキップ
        if not line:
            continue

        # コメント行をスキップ
        if line.startswith("#") or line.startswith("//"):
            continue

        # ヘッダー行をスキップ（辞書登録リスト等のセクション見出し）
        if re.match(r'^\d+\.\s', line) or line.startswith("辞書登録"):
            continue

        # メタデータセクション以降は台本終了とみなす
        if line.startswith("YouTubeメタデータ") or line.startswith("著作権侵害"):
            break

        # "キャラ名, セリフ" 形式を解析
        match = re.match(r'^([^,]+),\s*(.+)$', line)
        if match:
            speaker_raw = match.group(1).strip()
            text = match.group(2).strip()

            # 感情タグを抽出 [emotion:xxx]
            emotion_match = re.search(r'\[emotion:(\w+)\]', text)
            emotion = "normal"
            if emotion_match:
                emotion = emotion_match.group(1)
                text = re.sub(r'\[emotion:\w+\]', '', text).strip()

            # [impact:xxx] タグはtextに保持（scene_composerが検出に使用）
            # VOICEVOXへの送信時にscript_to_audio.pyで除去される

            # 感情タグ除去後に残るカンマを除去
            # 台本フォーマット: "話者, [emotion:xxx], テキスト"
            text = text.lstrip(',').lstrip()

            # キャラクター名を解決
            char_key = name_map.get(speaker_raw.lower())
            if char_key is None:
                # 辞書登録エントリ（短い読み仮名）は警告なしでスキップ
                if len(text) <= 10 and re.match(r'^[\u30A0-\u30FF]+$', text):
                    continue
                print(f"  警告: 不明なキャラクター '{speaker_raw}' (スキップ)", file=sys.stderr)
                continue

            # 辞書エントリのような短い行はスキップ（例: "Cameron,キャメロン"）
            if len(text) <= 10 and re.match(r'^[\u30A0-\u30FF]+$', text):
                continue

            # セクション確定判定
            # ナレーションモード: 毎行独立セクション / 対談モード: 話者変更時
            if current_speaker and current_lines:
                if split_per_line or current_speaker != char_key:
                    _flush_section(sections, current_speaker, current_lines, characters)
                    current_lines = []

            current_speaker = char_key
            current_lines.append((text, emotion))
        else:
            # カンマなしの行は前の話者の続きとして扱う
            if current_speaker and line:
                current_lines.append(line)

    # 最後のセクションを確定
    if current_speaker and current_lines:
        _flush_section(sections, current_speaker, current_lines, characters)

    return {"sections": sections}


def _flush_section(
    sections: List[Dict],
    speaker: str,
    lines: List[tuple],
    characters: Dict
) -> None:
    """セクションを確定してsections配列に追加する。"""
    char_data = characters[speaker]

    if not lines:
        return

    text = "".join([line[0] for line in lines])
    emotion = lines[-1][1]  # 最後の感情タグを使用

    if not text.strip():
        return

    sections.append({
        "index": len(sections),
        "speaker": speaker,
        "speaker_display": char_data["display_name"],
        "text": text,
        "emotion": emotion,
        "voicevox_speaker_id": char_data["voicevox"]["speaker_id"],
    })


def parse_script_file(
    script_path: str,
    config_path: Optional[str] = None
) -> Dict:
    """台本ファイルを読み込んで解析する。"""
    script_text = Path(script_path).read_text(encoding="utf-8")

    # コードブロックで囲まれている場合は中身を抽出
    code_block = re.search(r'```(?:text)?\n(.*?)```', script_text, re.DOTALL)
    if code_block:
        script_text = code_block.group(1)

    config = load_config(config_path)
    return parse_script(script_text, config)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        # デモ用サンプル（経済学テーマ）
        sample = """Amy, 皆さん、こんにちは。今日は金利とインフレの関係について解説するわ。
Shonen, えっ、金利ってなんすか？銀行に預けるとお金が増えるやつっすよね？
Amy, アンタねぇ、それだけじゃないのよ。金利は経済全体を動かす超重要な仕組みなの。
Amy, 日銀がマイナス金利を解除した意味、ちゃんと理解してる？
Shonen, マジっすか？全然わかんないっす…教えてください！"""
        print("=== サンプル台本の解析 ===")
        result = parse_script(sample)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        script_path = sys.argv[1]
        config_path = sys.argv[2] if len(sys.argv) > 2 else None
        result = parse_script_file(script_path, config_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
