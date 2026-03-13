#!/usr/bin/env python3
"""
2キャラVOICEVOX音声生成モジュール（エイミー先生の経済学）

script_parser.pyの出力（sections配列）を入力とし、
キャラクターごとに異なるVOICEVOX speaker_idで音声を生成する。

voicevox-api-tuning-guide.mdの知見を実装：
- 誤読修正辞書（経済用語対応）
- カギ括弧削除（音声用）
- 読点最適化（0.15秒）、文末最適化（0.25秒）
- 感情プリセット
"""

import json
import re
import wave
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional


# 誤読修正辞書（voicevox-api-tuning-guide.mdより + 経済用語の修正）
MISPRONUNCIATION_DICT = {
    # 汎用（全プロジェクト共通）
    "親ガチャ": "おやがちゃ",
    "SOS": "エスオーエス",
    "12歳": "じゅうにさい",
    "YouTube": "ユーチューブ",
    "iPhone": "アイフォーン",
    "iPad": "アイパッド",
    "iOS": "アイオーエス",
    "Apple": "アップル",
    "SE": "エスイー",
    "Plus": "プラス",
    "FaceTime": "フェイスタイム",
    "iMessage": "アイメッセージ",
    "Mac": "マック",
    "Logitech": "ロジテック",
    "ABEMA": "アベマ",
    "Prime": "プライム",
    # 経済用語（VOICEVOXが誤読しやすい）
    "GDP": "ジーディーピー",
    "FRB": "エフアールビー",
    "ECB": "イーシービー",
    "IMF": "アイエムエフ",
    "FOMC": "エフオーエムシー",
    "CPI": "シーピーアイ",
    "インフレ": "インフレ",
    "デフレ": "デフレ",
    "スタグフレーション": "スタグフレーション",
    "量的緩和": "りょうてきかんわ",
    "テーパリング": "テーパリング",
    "イールドカーブ": "イールドカーブ",
    "プライマリーバランス": "プライマリーバランス",
    "マイナス金利": "マイナスきんり",
    "利上げ": "りあげ",
    "利下げ": "りさげ",
    # 経済系人名・組織名
    "日銀": "にちぎん",
    "黒田総裁": "くろだそうさい",
    "植田総裁": "うえだそうさい",
    "FED": "フェド",
    "NISA": "ニーサ",
    "iDeCo": "イデコ",
    "ETF": "イーティーエフ",
    "REIT": "リート",
    "S&P": "エスアンドピー",
    "NASDAQ": "ナスダック",
    "NYSE": "ニューヨークしょうけんとりひきじょ",
    "TOPIX": "トピックス",
    # 中国・日本経済摩擦関連
    "信越化学": "しんえつかがく",
    "C919": "シーきゅういちきゅう",
    "軍民両用": "ぐんみんりょうよう",
    "南鳥島": "みなみとりしま",
    "国産化率": "こくさんかりつ",
    "40社": "よんじゅっしゃ",
    "84パーセント": "はちじゅうよんパーセント",
    "95パーセント": "きゅうじゅうごパーセント",
    "42パーセント": "よんじゅうにパーセント",
    "4割": "よんわり",
    "EUV": "イーユーブイ",
    "EEZ": "イーイーゼット",
    "JAMSTEC": "ジャムステック",
    # BYD・EV関連
    "BYD": "ビーワイディー",
    "EV": "イーブイ",
    "恒大集団": "こうだいしゅうだん",
    "バフェット": "バフェット",
    "300社": "さんびゃくしゃ",
    "4500兆円": "よんせんごひゃくちょうえん",
    "48兆円": "よんじゅうはっちょうえん",
    "8兆円": "はっちょうえん",
    "7800人": "ななせんはっぴゃくにん",
    "80パーセント": "はちじゅっパーセント",
    "65パーセント": "ろくじゅうごパーセント",
    "過当競争": "かとうきょうそう",
}

# 感情プリセット（voicevox-api-tuning-guide.md準拠: 控えめな調整が最善）
# ガイドライン: intonationScale 1.0〜1.2が自然、pitchScale調整は基本不要
# 注意: speedScaleはconfig.jsonで一元管理（1.3）。感情プリセットでは上書きしない
EMOTION_PRESETS = {
    "normal": {"pitchScale": 0.0, "intonationScale": 1.0, "volumeScale": 1.0},
    "excited": {"pitchScale": 0.02, "intonationScale": 1.15, "volumeScale": 1.05},
    "calm": {"pitchScale": 0.0, "intonationScale": 0.95, "volumeScale": 1.0},
    "sad": {"pitchScale": -0.02, "intonationScale": 0.9, "volumeScale": 0.95},
    "happy": {"pitchScale": 0.02, "intonationScale": 1.1, "volumeScale": 1.0},
    "whisper": {"pitchScale": -0.02, "intonationScale": 0.8, "volumeScale": 0.8},
}


def load_config(config_path: Optional[str] = None) -> Dict:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_voicevox(base_url: str = "http://localhost:50021") -> bool:
    """VOICEVOXサーバーへの接続確認"""
    try:
        req = urllib.request.Request(f"{base_url}/version")
        with urllib.request.urlopen(req, timeout=5) as res:
            version = res.read().decode().strip('"')
            print(f"  VOICEVOX v{version} 接続OK")
            return True
    except Exception as e:
        print(f"  VOICEVOX接続エラー: {e}")
        print("  起動: open /Applications/VOICEVOX.app")
        return False


def fix_mispronunciation(text: str) -> str:
    """誤読修正（voicevox-api-tuning-guide.mdより）"""
    for wrong, correct in MISPRONUNCIATION_DICT.items():
        text = text.replace(wrong, correct)
    return text


def remove_brackets(text: str) -> str:
    """カギ括弧削除（音声用・voicevox-api-tuning-guide.mdより）"""
    text = text.replace("「", "").replace("」", "")
    text = text.replace("『", "").replace("』", "")
    return text


def adjust_pauses(query: dict) -> dict:
    """間の長さを最適化（voicevox-api-tuning-guide.mdより）"""
    for phrase in query.get("accent_phrases", []):
        if "pause_mora" in phrase and phrase["pause_mora"]:
            pause_text = phrase["pause_mora"].get("text", "")
            if pause_text == "、":
                phrase["pause_mora"]["vowel_length"] = 0.15
            elif pause_text == "。":
                phrase["pause_mora"]["vowel_length"] = 0.25
    return query


def enhance_naturalness(query: dict, text: str) -> dict:
    """
    VOICEVOX音声の自然さを向上させる後処理。

    1. 疑問文の語尾上げ（is_interrogative）
    2. 発話前後の無音最適化（prePhonemeLength/postPhonemeLength）
    3. 文字数ベースの動的speedScale（短文は速く、長文はゆっくり）
    4. 抑揚を少しだけ増し（intonationScale 1.1）
    5. 重要キーワード前に戦略的ポーズ挿入
    """
    accent_phrases = query.get("accent_phrases", [])

    # 1. 疑問文検出 → is_interrogative フラグ設定
    stripped = text.rstrip()
    if stripped.endswith("？") or stripped.endswith("?"):
        if accent_phrases:
            accent_phrases[-1]["is_interrogative"] = True

    # 2. 発話前後の無音を短縮（セグメント間の接続を滑らかに）
    query["prePhonemeLength"] = 0.05
    query["postPhonemeLength"] = 0.05

    # 3. 文字数ベースの動的speedScale
    base_speed = query.get("speedScale", 1.3)
    char_count = len(text)
    if char_count < 20:
        query["speedScale"] = min(base_speed + 0.1, 1.4)   # 短文は速め
    elif char_count > 50:
        query["speedScale"] = max(base_speed - 0.1, 1.2)   # 長文はゆっくり

    # 4. 抑揚を少しだけ増し（normalプリセット=1.0の場合のみ）
    current_intonation = query.get("intonationScale", 1.0)
    if current_intonation == 1.0:
        query["intonationScale"] = 1.1

    # 5. 重要キーワード前に戦略的ポーズ挿入（経済用語を追加）
    emphasis_keywords = [
        # 汎用
        "信頼", "本質", "問題", "実は", "なんと", "つまり", "結局",
        "真実", "本当", "重要", "深刻", "衝撃", "驚き", "まさか",
        # 経済用語
        "金利", "インフレ", "デフレ", "円安", "円高", "株価",
        "暴落", "急騰", "景気", "不況", "バブル", "崩壊", "危機",
        "制裁", "依存", "棚上げ", "採掘", "心臓部", "正体", "握って",
    ]
    for i, phrase in enumerate(accent_phrases):
        phrase_text = "".join(m.get("text", "") for m in phrase.get("moras", []))
        for keyword in emphasis_keywords:
            if keyword in phrase_text and i > 0:
                prev = accent_phrases[i - 1]
                if not prev.get("pause_mora"):
                    prev["pause_mora"] = {
                        "text": "、",
                        "consonant": None,
                        "consonant_length": None,
                        "vowel": "pau",
                        "vowel_length": 0.20,
                        "pitch": 0.0
                    }
                break

    return query


def convert_to_oral_style(text: str) -> str:
    """
    書き言葉を話し言葉に変換（保守的・討論番組スタイル向け）。

    台本はユーザー作成のため、意味が変わらない安全な変換のみ実施。
    """
    # 「〜ている」→「〜てる」（最も一般的な口語化）
    text = re.sub(r'ている([。、！？\s]|$)', r'てる\1', text)
    # 「〜ていた」→「〜てた」
    text = re.sub(r'ていた([。、！？\s]|$)', r'てた\1', text)
    # 「〜ていない」→「〜てない」
    text = re.sub(r'ていない([。、！？\s]|$)', r'てない\1', text)
    # 「〜ていく」→「〜てく」
    text = re.sub(r'ていく([。、！？\s]|$)', r'てく\1', text)
    # 「〜ておく」→「〜とく」
    text = re.sub(r'ておく([。、！？\s]|$)', r'とく\1', text)
    # 「〜ではない」→「〜じゃない」
    text = re.sub(r'ではない([。、！？\s]|$)', r'じゃない\1', text)
    # 「〜ではなく」→「〜じゃなく」
    text = re.sub(r'ではなく', r'じゃなく', text)

    return text


def generate_audio_segment(
    text: str,
    speaker_id: int,
    output_path: Path,
    params: Dict[str, float],
    base_url: str = "http://localhost:50021"
) -> Optional[float]:
    """テキストからVOICEVOX音声を生成。Returns: 音声の長さ（秒）"""
    # 0. [impact:xxx] タグ除去（音声には不要）
    text = re.sub(r'\[impact:[^\]]+\]', '', text).strip()

    # 1. 誤読修正（最優先）
    processed_text = fix_mispronunciation(text)

    # 2. カギ括弧削除（音声用）
    processed_text = remove_brackets(processed_text)

    # 2.5. 口語体変換（自然な喋り口調に）
    processed_text = convert_to_oral_style(processed_text)

    # Step 3: audio_query
    query_params = urllib.parse.urlencode({"text": processed_text, "speaker": speaker_id})
    req = urllib.request.Request(
        f"{base_url}/audio_query?{query_params}", method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            query = json.loads(res.read().decode())
    except Exception as e:
        print(f"    クエリエラー: {e}")
        return None

    # 4. VOICEVOXパラメータ適用
    for key, value in params.items():
        if key in query:
            query[key] = value

    # 5. 間の最適化（読点0.15秒、文末0.25秒）
    query = adjust_pauses(query)

    # 5.5. 自然さ向上（疑問文語尾上げ + 発話前後無音最適化）
    query = enhance_naturalness(query, text)

    # Step 6: synthesis
    synth_params = urllib.parse.urlencode({"speaker": speaker_id, "enable_interrogative_upspeak": "true"})
    req = urllib.request.Request(
        f"{base_url}/synthesis?{synth_params}",
        data=json.dumps(query).encode(),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            audio_data = res.read()
    except Exception as e:
        print(f"    合成エラー: {e}")
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(audio_data)

    return get_wav_duration(output_path)


def estimate_query_duration(query: dict) -> float:
    """audio_queryレスポンスからモーラタイミングを合算して推定再生時間を計算"""
    total = query.get("prePhonemeLength", 0.0)
    for phrase in query.get("accent_phrases", []):
        for mora in phrase.get("moras", []):
            total += mora.get("consonant_length", 0.0) or 0.0
            total += mora.get("vowel_length", 0.0) or 0.0
        if phrase.get("pause_mora"):
            total += phrase["pause_mora"].get("vowel_length", 0.0) or 0.0
    total += query.get("postPhonemeLength", 0.0)
    return total


def get_wav_duration(wav_path: Path) -> float:
    with wave.open(str(wav_path), 'rb') as wf:
        return wf.getnframes() / float(wf.getframerate())


def split_into_sentences(text: str) -> List[str]:
    """テキストを文単位で分割（VOICEVOXは短文の方が品質が良い）"""
    sentences = re.split(r'(?<=[。！？])', text)
    return [s.strip() for s in sentences if s.strip()]


def concatenate_wav_files(wav_files: List[Path], output_path: Path, gap: float = 0.2):
    """複数のWAVファイルを結合（固定ギャップ付き）"""
    if not wav_files:
        return

    with wave.open(str(wav_files[0]), 'rb') as first_wav:
        params = first_wav.getparams()

    with wave.open(str(output_path), 'wb') as output_wav:
        output_wav.setparams(params)

        for i, wav_file in enumerate(wav_files):
            with wave.open(str(wav_file), 'rb') as input_wav:
                output_wav.writeframes(input_wav.readframes(input_wav.getnframes()))

            if i < len(wav_files) - 1:
                silence_frames = int(params.framerate * gap) * params.nchannels * params.sampwidth
                output_wav.writeframes(b'\x00' * silence_frames)


def concatenate_wav_files_dynamic(wav_files: List[Path], output_path: Path, gaps: List[float]):
    """複数のWAVファイルを結合（文ごとに異なるギャップ）"""
    if not wav_files:
        return

    with wave.open(str(wav_files[0]), 'rb') as first_wav:
        params = first_wav.getparams()

    with wave.open(str(output_path), 'wb') as output_wav:
        output_wav.setparams(params)

        for i, wav_file in enumerate(wav_files):
            with wave.open(str(wav_file), 'rb') as input_wav:
                output_wav.writeframes(input_wav.readframes(input_wav.getnframes()))

            if i < len(wav_files) - 1:
                gap = gaps[i] if i < len(gaps) else 0.15
                silence_frames = int(params.framerate * gap) * params.nchannels * params.sampwidth
                output_wav.writeframes(b'\x00' * silence_frames)


def generate_all_audio(
    sections: List[Dict],
    output_dir: Path,
    config: Optional[Dict] = None
) -> Optional[Dict[str, Any]]:
    """
    script_parser.pyの出力（sections配列）からキャラクターごとに音声を生成。

    Args:
        sections: script_parser.parse_script()["sections"]
        output_dir: 音声出力ディレクトリ
        config: config.json の内容

    Returns:
        audio_manifest dict
    """
    if config is None:
        config = load_config()

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    base_url = config.get("voicevox", {}).get("base_url", "http://localhost:50021")
    characters = config["characters"]

    if not check_voicevox(base_url):
        return None

    if not sections:
        print("  セクションが空です")
        return None

    print(f"  セクション数: {len(sections)}")

    segments = []

    for section in sections:
        idx = section["index"]
        speaker = section["speaker"]
        text = section["text"]
        speaker_id = section["voicevox_speaker_id"]
        emotion = section.get("emotion", "normal")

        # config.jsonからVOICEVOXパラメータ取得
        char_config = characters.get(speaker, {})
        vv_params = char_config.get("voicevox", {}).get("params", {}).copy()

        # 感情プリセットを適用（voicevox-api-tuning-guide.mdより）
        if emotion in EMOTION_PRESETS:
            emotion_params = EMOTION_PRESETS[emotion]
            for key, value in emotion_params.items():
                vv_params[key] = value
            print(f"    感情プリセット: {emotion}")

        # 文単位で分割して生成
        sentences = split_into_sentences(text)
        sentence_wavs = []
        sentence_timings = []  # 文ごとのタイミング情報
        # 文間ギャップを句読点に応じて動的に設定
        DEFAULT_SENTENCE_GAP = 0.15

        for j, sentence in enumerate(sentences):
            if not sentence.strip():
                continue

            wav_path = output_dir / f"segment_{idx+1:03d}_{j+1:02d}_{speaker}.wav"
            display = char_config.get("display_name", speaker)
            print(f"  [{idx+1}/{len(sections)}] ({display}) 「{sentence[:30]}...」")

            duration = generate_audio_segment(
                sentence, speaker_id, wav_path, vv_params, base_url
            )
            if duration:
                sentence_wavs.append(wav_path)
                sentence_timings.append({
                    "text": sentence,
                    "duration": round(duration, 6),
                })

        # セクション内の文を結合
        if sentence_wavs:
            segment_path = output_dir / f"segment_{idx+1:03d}_{speaker}.wav"

            # 文末の句読点に応じてギャップを動的設定
            sentence_gaps = []
            for j_idx in range(len(sentences) - 1):
                s = sentences[j_idx].rstrip()
                if s.endswith("！") or s.endswith("？") or s.endswith("!") or s.endswith("?"):
                    sentence_gaps.append(0.10)  # 感嘆・疑問→テンポよく
                else:
                    sentence_gaps.append(DEFAULT_SENTENCE_GAP)  # 通常

            concatenate_wav_files_dynamic(sentence_wavs, segment_path, gaps=sentence_gaps)

            # 個別ファイルを削除
            for sw in sentence_wavs:
                sw.unlink(missing_ok=True)

            # sentence_timingsにoffsetを計算（累積: duration + 動的gap）
            cumulative = 0.0
            for k, st in enumerate(sentence_timings):
                st["offset"] = round(cumulative, 6)
                cumulative += st["duration"]
                if k < len(sentence_timings) - 1:
                    gap = sentence_gaps[k] if k < len(sentence_gaps) else DEFAULT_SENTENCE_GAP
                    cumulative += gap

            # 字幕用テキストを保存（カギ括弧あり）
            subtitle_path = output_dir / f"segment_{idx+1:03d}_{speaker}_subtitle.txt"
            with open(subtitle_path, 'w', encoding='utf-8') as f:
                f.write(text)

            actual_duration = get_wav_duration(segment_path)
            segments.append({
                "index": idx,
                "file": segment_path.name,
                "subtitle_file": subtitle_path.name,
                "duration": actual_duration,
                "speaker": speaker,
                "speaker_display": char_config.get("display_name", speaker),
                "text": text,
                "emotion": emotion,
                "voicevox_speaker_id": speaker_id,
                "sentence_timings": sentence_timings,
            })

    if not segments:
        print("  音声が生成されませんでした")
        return None

    total_duration = sum(s["duration"] for s in segments)

    manifest = {
        "segments": segments,
        "total_duration": total_duration,
    }

    manifest_path = output_dir / "audio_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"  合計時間: {total_duration:.1f}秒 ({len(segments)}セグメント)")
    print(f"  マニフェスト: {manifest_path}")

    # プレビュー音声を自動生成（SEGMENT_GAP付き）
    segment_gap = config.get("audio", {}).get("segment_gap", 0.3)
    wav_files = [output_dir / s["file"] for s in segments]
    preview_path = output_dir / "preview_all.wav"
    concatenate_wav_files(wav_files, preview_path, gap=segment_gap)
    preview_duration = get_wav_duration(preview_path)
    print(f"  プレビュー: {preview_path} ({preview_duration:.1f}秒)")

    return manifest


if __name__ == "__main__":
    import argparse
    import sys
    from script_parser import parse_script, parse_script_file

    parser = argparse.ArgumentParser(description="2キャラVOICEVOX音声生成（経済学版）")
    parser.add_argument("script", help="台本ファイルパス")
    parser.add_argument("output_dir", nargs="?", default="./assets/audio",
                        help="出力ディレクトリ（デフォルト: ./assets/audio）")
    parser.add_argument("--output-dir", dest="output_dir_flag",
                        help="出力ディレクトリ（フラグ形式）")
    args = parser.parse_args()

    script_path = args.script
    output_dir = Path(args.output_dir_flag if args.output_dir_flag else args.output_dir)

    result = parse_script_file(script_path)
    sections = result["sections"]

    manifest = generate_all_audio(sections, output_dir)
    if manifest:
        print(f"\n完了: {len(manifest['segments'])}セグメント, 合計{manifest['total_duration']:.1f}秒")
