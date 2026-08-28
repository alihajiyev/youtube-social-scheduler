import os
import json
import time
import logging
import tempfile
import subprocess
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

GEMINI_API_KEYS = [k.strip() for k in os.getenv('GEMINI_API_KEYS', '').split(',') if k.strip()]

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
            "description": entry.get("summary", ""),
            "media_group": entry.get("media_group", {})
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


def generate_instagram_caption(video_title, video_link, video_description=""):
    description_text = video_description[:2000] if video_description else ""

    prompt = f"""Sen profesyonel bir Instagram sosyal medya uzmanisin. Asagidaki YouTube videosu icin tek bir profesyonel Instagram Reels caption yaz.

VIDEO BASLIGI: {video_title}

VIDEO ACIKLAMASI (transcript/konu ozeti):
{description_text}

KURALLAR:
- TAM 1 caption yaz, birden fazla secenek DEGIL
- Video hangi dildeyse caption O DILDE yaz (Turkce ise Turkce, Rusca ise Rusca, Ingilizce ise Ingilizce)
- Emoji kullan (3-5 tane, abartma)
- Cekici, merak uyandirici ve profesyonel ol
- 5-7 tane hashtag ekle (konuyla ilgili, buyuk ve kucuk harf karisik)
- Hashtag'leri caption'in ALTINA ayri satirda yaz
- Linki ekleme, sadece caption yaz
- Max 4-5 cumle olsun
- Tik gibi kisa ve vurucu olsun
- Sondaki hashtag'ler # ile baslasin

ORNEK (Turkce video icin):
Bu gercek sizi sasirtacak! Film dunyasindaki bu kucuk sirri biliyor muydunuz? 👀🔥

#sinema #film #merak #marvel #superkahraman

SADECE caption yaz, baska bir sey yazma, secenek sunma, baslik ekleme."""

    try:
        resp, _, _, _ = gemini.generate_content(prompt)
        caption = resp.text.strip()

        caption = caption.replace("**", "")
        caption = caption.replace("Seçenek 1:", "")
        caption = caption.replace("Seçenek 2:", "")
        caption = caption.replace("Seçenek 3:", "")
        caption = caption.replace("Seçenek 4:", "")
        caption = caption.replace("**Seçenek", "")

        lines = caption.split('\n')
        clean_lines = [l for l in lines if not l.strip().startswith('**Seçenek') and not l.strip().startswith('Seçenek')]
        caption = '\n'.join(clean_lines).strip()

        return caption
    except Exception as e:
        logger.error(f"Gemini caption hatasi: {e}")
        return f"🎬 {video_title}\n\n#YouTube #Video"


def download_youtube_video(video_url):
    try:
        tmp_dir = tempfile.mkdtemp()
        output_path = os.path.join(tmp_dir, "video.mp4")

        cmd = [
            "python", "-m", "yt_dlp",
            "-f", "bestvideo[height<=1080]+bestaudio/best",
            "--merge-output-format", "mp4",
            "--js-runtimes", "deno",
            "--remote-components", "ejs:github",
            "--cookies", "cookies.txt",
            "--extractor-args", "youtube:player_client=tv,web",
            "--no-playlist",
            "--no-progress",
            "-o", output_path,
            video_url
        ]

        logger.info(f"Komut: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        logger.info(f"yt-dlp returncode: {result.returncode}")
        if result.stdout:
            logger.info(f"yt-dlp stdout: {result.stdout[:500]}")
        if result.stderr:
            logger.info(f"yt-dlp stderr: {result.stderr[:500]}")

        if os.path.exists(output_path):
            logger.info(f"Video indirildi: {output_path}")
            return output_path

        for f in os.listdir(tmp_dir):
            if f.endswith(('.mp4', '.webm', '.mkv')):
                found = os.path.join(tmp_dir, f)
                logger.info(f"Bulunan video dosyasi: {found}")
                return found

        logger.error(f"Tmp dizininde video yok: {os.listdir(tmp_dir)}")
        return None
    except Exception as e:
        logger.error(f"Video indirme hatasi: {e}")
        return None


def upload_to_catbox(file_path):
    try:
        with open(file_path, 'rb') as f:
            response = requests.post(
                'https://catbox.moe/user/api.php',
                data={'reqtype': 'fileupload', 'userhash': ''},
                files={'fileToUpload': ('video.mp4', f, 'video/mp4')},
                timeout=120
            )

        if response.status_code == 200 and response.text.startswith('http'):
            return response.text.strip()
        return None
    except Exception as e:
        logger.error(f"Catbox yukleme hatasi: {e}")
        return None


def create_instagram_reels(video, access_token, business_account_id):
    try:
        caption = generate_instagram_caption(video["title"], video["link"], video.get("description", ""))
        logger.info(f"Olusturulan caption: {caption}")

        logger.info("Video indiriliyor...")
        video_path = download_youtube_video(video["link"])

        if not video_path:
            logger.error("Video indirilemedi!")
            return False

        logger.info("Video catbox'a yukleniyor...")
        video_url = upload_to_catbox(video_path)

        try:
            os.remove(video_path)
            os.rmdir(os.path.dirname(video_path))
        except:
            pass

        if not video_url:
            logger.error("Video yuklenemedi!")
            return False

        logger.info(f"Video URL: {video_url}")

        url = f"https://graph.facebook.com/v18.0/{business_account_id}/media"
        payload = {
            'media_type': 'REELS',
            'caption': caption,
            'share_to_feed': 'true',
            'access_token': access_token,
            'video_url': video_url
        }

        response = requests.post(url, data=payload)

        if response.status_code == 200:
            container_id = response.json().get('id')
            logger.info(f"Instagram container olusturuldu: {container_id}")

            for i in range(40):
                time.sleep(5)
                check = requests.get(
                    f"https://graph.facebook.com/v18.0/{container_id}",
                    params={'fields': 'status_code', 'access_token': access_token}
                )
                status = check.json().get('status_code', '')
                logger.info(f"  Durum: {status} ({(i+1)*5}s)")

                if status == 'FINISHED':
                    break
                elif status == 'ERROR':
                    logger.error(f"Video isleme hatasi: {check.json()}")
                    return False

            if status != 'FINISHED':
                logger.error("Video isleme zaman asimi!")
                return False

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


def check_and_post():
    channel_id = os.getenv('YOUTUBE_CHANNEL_ID', 'UCDxooL2M22LvKI32dREyjfQ')
    instagram_token = os.getenv('INSTAGRAM_ACCESS_TOKEN')
    instagram_business_id = os.getenv('INSTAGRAM_BUSINESS_ACCOUNT_ID')
    force_video_id = os.getenv('FORCE_VIDEO_ID')

    if force_video_id:
        logger.info(f"TEST MODU: Video {force_video_id} zorla paylasiliyor...")
        all_videos = get_youtube_feed(channel_id)
        new_videos = [v for v in all_videos if v["id"] == force_video_id]
        if not new_videos:
            logger.error(f"Video bulunamadi: {force_video_id}")
            return
    else:
        logger.info("Son 1 saatteki videolar kontrol ediliyor...")
        new_videos = get_new_videos_last_hour(channel_id)

    if not new_videos:
        logger.info("Son 1 saatte yeni video bulunamadi.")
        return

    logger.info(f"{len(new_videos)} yeni video bulundu.")

    for video in new_videos:
        logger.info(f"Paylasiliyor: {video['title']}")

        if instagram_token and instagram_business_id:
            success = create_instagram_reels(video, instagram_token, instagram_business_id)
            if not success:
                logger.error(f"Video paylasilamadi: {video['title']}, tekrar denenecek.")
                continue
        else:
            logger.error("Instagram token veya business ID eksik!")
            continue

        mark_as_posted(video['id'])
        time.sleep(5)


def mark_as_posted(video_id):
    posted_data = load_posted_videos()
    posted_data["posted"].append(video_id)
    save_posted_videos(posted_data)


def commit_posted_videos():
    try:
        import subprocess
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", "posted_videos.json"], check=True)
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", "Update posted_videos.json"], check=True)
            subprocess.run(["git", "push"], check=True)
            logger.info("posted_videos.json guncellendi ve push edildi.")
        else:
            logger.info("posted_videos.json degisiklik yok.")
    except Exception as e:
        logger.error(f"Git push hatasi: {e}")


if __name__ == "__main__":
    try:
        check_and_post()
        commit_posted_videos()
    except Exception as e:
        import traceback
        traceback.print_exc()
