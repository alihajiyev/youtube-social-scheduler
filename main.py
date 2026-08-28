import os
import json
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import requests
from dotenv import load_dotenv

from gemini_manager import GeminiManager

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DATA_FILE = Path("posted_videos.json")

GEMINI_API_KEYS = [
    "AIzaSyAOVYXnN36rbEM0wc3ettzbzUHyx-Exves",
    "AIzaSyB7vmUprtwBHhsCSb8urZqHHn5rTEPB8EE",
    "AIzaSyCvC9qF29SIgFsLMvdiruiBqR2qmx70nCE",
    "AIzaSyB6v1IQYhAyoZ8qK957sG-mW5gijCbNO-A",
    "AIzaSyDIuxRyLpYlhD5tM7tPdxfW0hhuXMwHwd0",
    "AIzaSyDMKFusKDyY3ude89ivxAKxvMsXlbNpm7E",
]

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-3-flash",
    "gemini-3.1-flash-lite",
]

gemini = GeminiManager(GEMINI_API_KEYS, GEMINI_MODELS)


def load_posted_videos():
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {"posted": []}


def save_posted_videos(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)


def get_youtube_feed(channel_id):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(url)
    videos = []
    for entry in feed.entries:
        published = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        videos.append({
            "id": entry.yt_videoid,
            "title": entry.title,
            "link": entry.link,
            "published": published,
            "published_str": entry.published,
            "description": entry.get("summary", "")
        })
    return videos


def get_new_videos_last_hour(channel_id):
    posted_data = load_posted_videos()
    all_videos = get_youtube_feed(channel_id)
    now = datetime.now(timezone.utc)
    one_hour_ago = now - timedelta(hours=1)

    new_videos = []
    for v in all_videos:
        if v["id"] in posted_data["posted"]:
            continue
        if v["published"] >= one_hour_ago:
            new_videos.append(v)

    return new_videos


def generate_instagram_caption(video_title, video_link):
    prompt = f"""Sen bir Instagram sosyal medya uzmanisin. Asagidaki YouTube videosu icin Instagram'a uygun bir Reels caption yaz.

Video Basligi: {video_title}
Video Linki: {video_link}

Kurallar:
- Emoji'ler kullan (ama abartma, 3-5 tane yeter)
- Cekici ve merak uyandirici olsun
- 2-3 tane hashtag ekle (#YouTube #Video gibi degil, konuyla ilgili)
- Linki caption'in sonuna ekle
- Kisa ve oz olsun (max 2-3 cumle)
- Turkce yaz

Ornek:
🎬 Bu gercek sizi sasirtacak! 

Film dunyasindaki bu kucuk sirri biliyor muydunuz? 👀🔥

#sinema #film #merak

🔗 Videoyu izle: https://youtube.com/watch?v=xxx

Sadece caption'i yaz, baska bir sey yazma."""

    try:
        resp, _, _, _ = gemini.generate_content(prompt)
        caption = resp.text.strip()

        if video_link not in caption:
            caption = f"{caption}\n\n🔗 Videoyu izle: {video_link}"

        return caption
    except Exception as e:
        logger.error(f"Gemini caption hatasi: {e}")
        return f"🎬 {video_title}\n\n🔗 Videoyu izle: {video_link}\n\n#YouTube #Video"


def create_instagram_reels(video, access_token, business_account_id):
    try:
        caption = generate_instagram_caption(video["title"], video["link"])
        logger.info(f"Olusturulan caption: {caption}")

        video_id = video["id"]
        thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

        url = f"https://graph.facebook.com/v18.0/{business_account_id}/media"
        payload = {
            'media_type': 'REELS',
            'caption': caption,
            'share_to_feed': 'true',
            'access_token': access_token,
            'image_url': thumbnail_url
        }

        response = requests.post(url, data=payload)

        if response.status_code == 200:
            container_id = response.json().get('id')
            logger.info(f"Instagram container olusturuldu: {container_id}")

            time.sleep(10)

            publish_url = f"https://graph.facebook.com/v18.0/{business_account_id}/media_publish"
            publish_payload = {
                'creation_id': container_id,
                'access_token': access_token
            }
            publish_response = requests.post(publish_url, data=publish_payload)

            if publish_response.status_code == 200:
                logger.info("Instagram Reels paylasimi basarili!")
                return True
            else:
                logger.error(f"Instagram publish hatasi: {publish_response.text}")
                return False
        else:
            logger.error(f"Instagram container hatasi: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Instagram hatasi: {e}")
        return False


def post_to_tiktok(video, access_token):
    try:
        caption = f"{video['title']} #YouTube #Video"
        url = "https://open.tiktokapis.com/v2/post/publish/video/link/fetch/"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        payload = {
            'post_info': {
                'title': caption,
                'privacy_level': 'PUBLIC_TO_EVERYONE',
                'disable_duet': False,
                'disable_comment': False,
                'disable_stitch': False
            },
            'source_info': {
                'source': 'PULL_FROM_YOUTUBE',
                'youtube_video_url': video['link']
            }
        }

        response = requests.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if data.get('data', {}).get('publish_id'):
                logger.info("TikTok paylasimi basarili!")
                return True
            else:
                logger.error(f"TikTok yanit hatasi: {data}")
                return False
        else:
            logger.error(f"TikTok hatasi: {response.text}")
            return False
    except Exception as e:
        logger.error(f"TikTok hatasi: {e}")
        return False


def check_and_post():
    channel_id = os.getenv('YOUTUBE_CHANNEL_ID', 'UCDxooL2M22LvKI32dREyjfQ')
    instagram_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
    instagram_business_id = os.getenv('INSTAGRAM_BUSINESS_ACCOUNT_ID')
    tiktok_token = os.getenv('TIKTOK_ACCESS_TOKEN')

    logger.info("Son 1 saatteki videolar kontrol ediliyor...")
    new_videos = get_new_videos_last_hour(channel_id)

    if not new_videos:
        logger.info("Son 1 saatte yeni video bulunamadi.")
        return

    logger.info(f"{len(new_videos)} yeni video bulundu.")

    for video in new_videos:
        logger.info(f"Paylasiliyor: {video['title']}")

        if instagram_token and instagram_business_id:
            create_instagram_reels(video, instagram_token, instagram_business_id)

        if tiktok_token:
            post_to_tiktok(video, tiktok_token)

        mark_as_posted(video['id'])
        time.sleep(5)


def mark_as_posted(video_id):
    posted_data = load_posted_videos()
    posted_data["posted"].append(video_id)
    save_posted_videos(posted_data)


if __name__ == "__main__":
    check_and_post()
