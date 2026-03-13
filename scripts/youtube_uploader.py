#!/usr/bin/env python3
"""
YouTube動画アップローダー — エイミー先生の経済学

YouTube Data API v3 を使用して動画をアップロードする。
初回はOAuth認証が必要（ブラウザが開く）。以降はtoken_economics.jsonで自動認証。

使い方:
  # 認証テスト
  python scripts/youtube_uploader.py --auth-test

  # Shortsアップロード（非公開）
  python scripts/youtube_uploader.py \\
    --video "samples/中国が隠した日本依存の闇/shorts_a_v9.mp4" \\
    --title "中国が隠してた日本依存の闇" \\
    --description-body "中国経済の日本依存について解説" \\
    --tags "中国経済,日本,依存"

  # 公開に変更
  python scripts/youtube_uploader.py --publish VIDEO_ID
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

PROJECT_ROOT = Path(__file__).parent.parent
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]
CLIENT_SECRET = PROJECT_ROOT / "client_secret.json"
TOKEN_FILE = PROJECT_ROOT / "token_economics.json"

# YouTube カテゴリID
CATEGORY_EDUCATION = "27"  # Education

# チャンネル設定
CHANNEL_NAME = "エイミー先生の経済学"
CHANNEL_ID = "UCGRxKUpwwj6veSrzT3cyBlg"

# アップロードログ
UPLOAD_LOG = PROJECT_ROOT / "upload_log.json"

# ===== 概要欄テンプレート =====

# Shorts用（メイン）
# YouTubeはShortsで先頭3つのハッシュタグをタイトル下に表示する
# --hashtagsで3つ指定（テーマ固有）
SHORTS_DESCRIPTION_TEMPLATE = """{hashtags}

{body}

📺 チャンネル登録: https://www.youtube.com/@エイミー先生の経済学?sub_confirmation=1
💬 コメントで意見を教えてね！

⚠️ 本動画は経済に関する情報提供と知識共有を目的とした教育エンターテインメントです。
投資勧誘や専門的な投資助言を提供するものではありません。
一部の素材はAI技術を用いて制作されています。"""

# 長尺用（将来用）
# 参考: アニメで世界経済の動画要約+目次スタイル
LONG_DESCRIPTION_TEMPLATE = """{body}

📺 チャンネル登録はこちらから！
あなたの登録がエイミー先生の機嫌を良くします（たぶん）。
👉 https://www.youtube.com/@エイミー先生の経済学?sub_confirmation=1

👍 高評価とコメントも待ってるぜ！（by 少年）
「勉強になった！」「もっとやって！」「エイミー先生厳しい！」など、
感想をコメント欄で教えてくれると嬉しいです！

━━━━━━━━━━━━━━━━
🎓 登場人物紹介
━━━━━━━━━━━━━━━━
👩‍🏫 エイミー（先生）
論理的で毒舌な美女教師。
経済の常識をバッサリ切るのが趣味（？）。
「アンタたち、ちゃんと自分の頭で考えてる？」

👦 少年（生徒）
素朴な疑問をぶつけるちょっぴりノーテンキな男子。
すぐネットの噂を信じちゃうけど、根はいいヤツ。
「へぇ〜、そうだったんすか！知らなかったっす！」

━━━━━━━━━━━━━━━━
⚠️ 免責事項・著作権について
━━━━━━━━━━━━━━━━
当チャンネルは、経済ニュースや社会問題についての解説・考察を行う教育エンターテインメント・チャンネルです。
投資助言ではありません。投資判断はご自身の責任でお願いします。
動画内で使用している素材（画像・動画・音声）の著作権は、それぞれの権利所有者に帰属します。
万が一、動画の内容に問題がある場合は、権利者様より直接ご連絡いただければ速やかに対応いたします。

※当チャンネルのシナリオ・構成・キャラクター設定の無断転載・模倣は固くお断りします。

{hashtags}"""

# ===== タグ =====

# Shorts用共通タグ
SHORTS_DEFAULT_TAGS = [
    "エイミー先生", "経済学", "経済ニュース", "経済解説",
    "Shorts", "ショート動画", "わかりやすく解説", "教育",
]

# 長尺用共通タグ
LONG_DEFAULT_TAGS = [
    "エイミー先生", "エイミー先生の経済学", "経済学", "経済ニュース",
    "経済解説", "わかりやすく解説", "教育", "時事経済",
]


def authenticate():
    """OAuth2認証。"""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print(f"トークンを更新中... ({CHANNEL_NAME})")
            creds.refresh(Request())
        else:
            if not CLIENT_SECRET.exists():
                print(f"エラー: {CLIENT_SECRET} が見つかりません。")
                sys.exit(1)

            print(f"ブラウザでGoogleアカウント認証を行ってください...")
            print(f"  対象チャンネル: {CHANNEL_NAME}")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=8090)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
        print(f"認証情報を保存: {TOKEN_FILE}")

    return creds


def log_upload(video_id, title, video_path, privacy, is_shorts=False):
    """アップロード履歴をupload_log.jsonに記録。"""
    log = []
    if UPLOAD_LOG.exists():
        with open(UPLOAD_LOG, "r", encoding="utf-8") as f:
            log = json.load(f)

    log.append({
        "video_id": video_id,
        "title": title,
        "video_path": str(video_path),
        "privacy": privacy,
        "is_shorts": is_shorts,
        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })

    with open(UPLOAD_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def detect_shorts(video_path):
    """動画がShortsかどうかを自動判定（縦長 + 3分以内）。"""
    probe = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json',
         '-show_streams', '-show_format', video_path],
        capture_output=True, text=True
    )
    if probe.returncode != 0:
        return False
    data = json.loads(probe.stdout)
    video_stream = next((s for s in data.get('streams', [])
                         if s['codec_type'] == 'video'), None)
    if not video_stream:
        return False
    w = int(video_stream.get('width', 0))
    h = int(video_stream.get('height', 0))
    duration = float(data.get('format', {}).get('duration', 999))
    return h > w and duration <= 180


def validate_video(video_path):
    """アップロード前の動画整合性チェック。"""
    print(f"動画ファイル検証中: {video_path}")
    probe = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
         '-show_entries', 'stream=codec_name,width,height,duration,nb_frames',
         '-of', 'json', video_path],
        capture_output=True, text=True
    )
    if probe.returncode != 0 or not probe.stdout.strip():
        print(f"エラー: ffprobeが失敗しました。動画ファイルが破損している可能性があります。")
        print(f"  stderr: {probe.stderr[:500]}")
        sys.exit(1)

    probe_data = json.loads(probe.stdout)
    if not probe_data.get('streams'):
        print(f"エラー: 動画ストリームが見つかりません。")
        sys.exit(1)

    # NALユニットエラーチェック
    error_check = subprocess.run(
        ['ffprobe', '-v', 'error', '-i', video_path],
        capture_output=True, text=True
    )
    error_lines = [l for l in error_check.stderr.splitlines()
                   if 'Invalid NAL' in l or 'Error splitting' in l]
    if len(error_lines) > 5:
        print(f"エラー: H.264ストリームが破損しています（NALエラー {len(error_lines)}件検出）。")
        sys.exit(1)

    stream = probe_data['streams'][0]
    print(f"  検証OK: {stream.get('codec_name', '?')} "
          f"{stream.get('width', '?')}x{stream.get('height', '?')}")
    return True


def upload_video(youtube, video_path, title, description, tags, category_id,
                 privacy="private"):
    """動画をアップロード（resumable upload）。"""
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": "ja",
            "defaultAudioLanguage": "ja",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "embeddable": True,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"アップロード開始: {video_path}")
    file_size = os.path.getsize(video_path)
    print(f"ファイルサイズ: {file_size / 1024 / 1024:.1f}MB")

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  {pct}% アップロード完了")

    video_id = response["id"]
    print(f"\nアップロード完了!")
    print(f"  Video ID: {video_id}")
    print(f"  URL: https://www.youtube.com/watch?v={video_id}")
    print(f"  Studio: https://studio.youtube.com/video/{video_id}/edit")
    print(f"  公開状態: {privacy}")

    return video_id


def set_thumbnail(youtube, video_id, thumbnail_path):
    """サムネイルを設定。"""
    if not os.path.exists(thumbnail_path):
        print(f"警告: サムネイル {thumbnail_path} が見つかりません。スキップします。")
        return False

    media = MediaFileUpload(thumbnail_path, mimetype="image/jpeg")
    youtube.thumbnails().set(videoId=video_id, media_body=media).execute()
    print(f"サムネイル設定完了: {thumbnail_path}")
    return True


def publish_video(youtube, video_id):
    """非公開/限定公開の動画を公開に変更。"""
    answer = input(f"動画 {video_id} を公開しますか？ (y/N): ").strip().lower()
    if answer != 'y':
        print("公開をキャンセルしました")
        return
    youtube.videos().update(
        part="status",
        body={
            "id": video_id,
            "status": {"privacyStatus": "public"},
        }
    ).execute()
    print(f"公開に変更しました: https://youtube.com/shorts/{video_id}")


def main():
    parser = argparse.ArgumentParser(
        description="YouTube動画アップローダー — エイミー先生の経済学")
    parser.add_argument("--auth-test", action="store_true",
                        help="認証テストのみ実行")
    parser.add_argument("--video", type=str,
                        help="アップロードする動画ファイルパス")
    parser.add_argument("--title", type=str, help="動画タイトル")
    parser.add_argument("--description", type=str, default="",
                        help="動画の説明文（フル指定。--description-bodyより優先）")
    parser.add_argument("--description-body", type=str, default="",
                        help="動画固有の概要（テンプレートと自動結合）")
    parser.add_argument("--hashtags", type=str, default="",
                        help="ハッシュタグ3つ（例: '#中国経済 #原油 #地政学'）")
    parser.add_argument("--tags", type=str, default="",
                        help="カンマ区切りのタグ（共通タグに追加）")
    parser.add_argument("--thumbnail", type=str, default=None,
                        help="サムネイル画像パス")
    parser.add_argument("--privacy", type=str, default="private",
                        choices=["private", "unlisted", "public"],
                        help="公開状態 (デフォルト: private)")
    parser.add_argument("--long", action="store_true",
                        help="長尺モード（概要欄・タグが長尺用になる）")
    parser.add_argument("--publish", type=str, default=None,
                        help="指定video_idを公開に変更（アップロードなし）")
    args = parser.parse_args()

    # 認証
    creds = authenticate()

    if args.auth_test:
        youtube = build("youtube", "v3", credentials=creds)
        channels = youtube.channels().list(part="snippet", mine=True).execute()
        if channels.get("items"):
            ch = channels["items"][0]["snippet"]
            print(f"認証テスト成功!")
            print(f"  チャンネル名: {ch['title']}")
            print(f"  チャンネルID: {channels['items'][0]['id']}")
        else:
            print("認証成功ですが、チャンネルが見つかりません。")
        return

    # --publish モード
    if args.publish:
        youtube = build("youtube", "v3", credentials=creds)
        publish_video(youtube, args.publish)
        return

    # アップロード
    if not args.video:
        parser.error("--video は必須です（--auth-test / --publish以外）")
    if not args.title:
        parser.error("--title は必須です")
    if not os.path.exists(args.video):
        print(f"エラー: 動画ファイルが見つかりません: {args.video}")
        sys.exit(1)

    # Shorts自動判定
    is_shorts = not args.long and detect_shorts(args.video)
    if is_shorts:
        print(f"Shorts動画を検出しました（縦長 + 3分以内）")

    # 動画検証
    validate_video(args.video)

    youtube = build("youtube", "v3", credentials=creds)

    # 説明文の構築
    # ハッシュタグは3つ（先頭配置→YouTubeがタイトル下に表示）
    if args.description:
        description = args.description
    elif args.description_body:
        hashtags = args.hashtags if args.hashtags else "#経済 #経済ニュース #解説"
        if not is_shorts or args.long:
            description = LONG_DESCRIPTION_TEMPLATE.format(
                body=args.description_body,
                hashtags=hashtags
            )
        else:
            description = SHORTS_DESCRIPTION_TEMPLATE.format(
                body=args.description_body,
                hashtags=hashtags
            )
    else:
        description = ""

    # タグの構築
    custom_tags = [t.strip() for t in args.tags.split(",")
                   if t.strip()] if args.tags else []
    base_tags = LONG_DEFAULT_TAGS if args.long else SHORTS_DEFAULT_TAGS
    tags = base_tags + [t for t in custom_tags if t not in base_tags]

    # Shortsタイトルに#Shortsが含まれていなければ追加
    title = args.title
    if is_shorts and "#Shorts" not in title:
        title = f"{title} #Shorts"

    video_id = upload_video(
        youtube, args.video, title, description,
        tags, CATEGORY_EDUCATION, args.privacy
    )

    # アップロードログ記録
    log_upload(video_id, title, args.video, args.privacy, is_shorts)

    # サムネイル設定
    if args.thumbnail:
        time.sleep(2)
        set_thumbnail(youtube, video_id, args.thumbnail)

    url = (f"https://youtube.com/shorts/{video_id}" if is_shorts
           else f"https://www.youtube.com/watch?v={video_id}")
    print(f"\n完了!")
    print(f"  Video ID: {video_id}")
    print(f"  URL: {url}")
    print(f"  Studio: https://studio.youtube.com/video/{video_id}/edit")
    print(f"  チャンネル: {CHANNEL_NAME}")
    print(f"  公開状態: {args.privacy}")
    if args.privacy == "private":
        print(f"\n  公開するには: python scripts/youtube_uploader.py --publish {video_id}")


if __name__ == "__main__":
    main()
