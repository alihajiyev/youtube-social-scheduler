import os
import re
import json
import tempfile
import subprocess
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import requests
from google import genai

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

DATA_FILE = Path("posted_videos.json")
CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID", "UCDxooL2M22LvKI32dREyjfQ")

INVIDIOUS_INSTANCES = [
    "https://inv.nadeko.net",
    "https://invidious.nerdvpn.de",
    "https://invidious.f5.si",
    "https://yt.chocolatemoo53.com",
]


def load_posted():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"posted": []}


def save_posted(data):
    DATA_FILE.write_text(json.dumps(data, indent=2))


def mark_posted(vid):
    d = load_posted()
    d["posted"].append(vid)
    save_posted(d)


def commit_posted():
    try:
        subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", "posted_videos.json"], check=True)
        r = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
        if r.returncode != 0:
            subprocess.run(["git", "commit", "-m", "update posted"], check=True)
            subprocess.run(["git", "push"], check=True)
            log.info("posted_videos.json pushed")
    except Exception as e:
        log.error(f"git push error: {e}")


def get_feed(channel_id):
    feed = feedparser.parse(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    videos = []
    for e in feed.entries:
        pub = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        videos.append({"id": e.yt_videoid, "title": e.title, "link": e.link, "published": pub, "description": e.get("summary", "")})
    return videos


def get_new_videos(channel_id):
    posted = load_posted()["posted"]
    now = datetime.now(timezone.utc)
    return [v for v in get_feed(channel_id) if v["id"] not in posted and v["published"] >= now - timedelta(hours=2)]


def extract_video_id(url):
    patterns = [r'(?:v=|/)([\w-]{11})', r'(?:youtu\.be/)([\w-]{11})']
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def download_via_invidious(video_url):
    video_id = extract_video_id(video_url)
    if not video_id:
        log.error(f"Could not extract video ID from: {video_url}")
        return None

    for instance in INVIDIOUS_INSTANCES:
        try:
            api_url = f"{instance}/api/v1/videos/{video_id}?fields=adaptiveFormats,formatStreams,title"
            log.info(f"Invidious API: {api_url}")
            r = requests.get(api_url, timeout=30)
            if r.status_code != 200:
                log.warning(f"Invidious {instance} returned {r.status_code}")
                continue

            data = r.json()
            title = data.get("title", "unknown")
            log.info(f"Invidious title: {title}")

            format_streams = data.get("formatStreams", [])
            adaptive = data.get("adaptiveFormats", [])

            mp4_streams = [s for s in format_streams if "mp4" in s.get("type", "")]

            if not mp4_streams:
                mp4_streams = [s for s in adaptive if "video/mp4" in s.get("type", "") and "audio" not in s.get("type", "")]

            if not mp4_streams:
                log.warning(f"No MP4 streams found on {instance}")
                continue

            best = sorted(mp4_streams, key=lambda x: int(x.get("resolution", "0p").replace("p", "") or 0), reverse=True)
            selected = None
            for s in best:
                res = int(s.get("resolution", "0p").replace("p", "") or 0)
                if res <= 1080:
                    selected = s
                    break
            if not selected:
                selected = best[0]

            stream_url = selected.get("url")
            if not stream_url:
                log.warning(f"No URL in stream from {instance}")
                continue

            log.info(f"Downloading from Invidious: {selected.get('resolution', '?')} ({selected.get('type', '?')})")

            tmp = tempfile.mkdtemp()
            out = os.path.join(tmp, "video.mp4")

            vid_r = requests.get(stream_url, stream=True, timeout=300)
            with open(out, 'wb') as f:
                for chunk in vid_r.iter_content(chunk_size=8192):
                    f.write(chunk)

            if os.path.exists(out) and os.path.getsize(out) > 100000:
                log.info(f"Invidious download success: {out} ({os.path.getsize(out)} bytes)")
                return out

        except Exception as e:
            log.warning(f"Invidious {instance} error: {e}")
            continue

    return None


def download_via_ytdlp(video_url):
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, "video.mp4")

    cookies_content = os.getenv("YOUTUBE_COOKIES")
    if cookies_content:
        cookie_path = os.path.join(tmp, "cookies.txt")
        import base64
        with open(cookie_path, "wb") as f:
            f.write(base64.b64decode(cookies_content))
    else:
        cookie_path = "cookies.txt"

    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=1080]+bestaudio/best",
        "--merge-output-format", "mp4",
        "--cookies", cookie_path,
        "--extractor-args", "youtube:player_client=web_creator,web",
        "--remote-components", "ejs:github",
        "--no-playlist",
        "--no-progress",
        "--socket-timeout", "60",
        "-o", out,
        video_url
    ]

    log.info(f"yt-dlp fallback: {video_url}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        log.info(f"yt-dlp exit: {r.returncode}")
        if r.stderr:
            log.info(f"stderr: {r.stderr[:300]}")
    except Exception as e:
        log.error(f"yt-dlp error: {e}")
        return None

    if os.path.exists(out) and os.path.getsize(out) > 100000:
        return out

    for f in os.listdir(tmp):
        if f.endswith((".mp4", ".webm", ".mkv")):
            return os.path.join(tmp, f)

    return None


def download_video(video_url):
    log.info("Trying Invidious API first...")
    result = download_via_invidious(video_url)
    if result:
        return result

    log.info("Invidious failed, trying yt-dlp fallback...")
    return download_via_ytdlp(video_url)


def generate_caption(title, description=""):
    keys = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()]
    if not keys:
        return f"🎬 {title}\n\n#YouTube #Video"

    prompt = f"""Sen profesyonel bir Instagram sosyal medya uzmanisin. Asagidaki YouTube videosu icin tek bir profesyonel Instagram Reels caption yaz.

VIDEO BASLIGI: {title}
VIDEO ACIKLAMASI: {description[:2000]}

KURALLAR:
- TAM 1 caption yaz
- Video hangi dildeyse caption O DILDE yaz
- Emoji kullan (3-5 tane)
- Cekici ve profesyonel ol
- 5-7 hashtag ekle
- Max 4-5 cumle

SADECE caption yaz."""

    for key in keys:
        try:
            c = genai.Client(api_key=key)
            resp = c.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            return resp.text.strip().replace("**", "")
        except Exception as e:
            log.warning(f"Gemini key {key[:12]} failed: {e}")
            continue

    return f"🎬 {title}\n\n#YouTube #Video"


def upload_to_catbox(file_path):
    try:
        log.info(f"Catbox upload: {file_path}")
        with open(file_path, 'rb') as f:
            r = requests.post(
                'https://catbox.moe/user/api.php',
                data={'reqtype': 'fileupload', 'userhash': ''},
                files={'fileToUpload': ('video.mp4', f, 'video/mp4')},
                timeout=180
            )
        log.info(f"Catbox response: {r.status_code} {r.text[:200]}")
        if r.status_code == 200 and r.text.startswith('http'):
            return r.text.strip()
        return None
    except Exception as e:
        log.error(f"Catbox error: {e}")
        return None


def publish_to_instagram(video_url, caption):
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    biz_id = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    if not token or not biz_id:
        log.error("Instagram token or business ID missing!")
        return False

    url = f"https://graph.facebook.com/v18.0/{biz_id}/media"
    payload = {
        'media_type': 'REELS',
        'caption': caption,
        'share_to_feed': 'true',
        'access_token': token,
        'video_url': video_url
    }

    r = requests.post(url, data=payload)
    if r.status_code != 200:
        log.error(f"Container error: {r.text}")
        return False

    container_id = r.json().get('id')
    log.info(f"Container created: {container_id}")

    for i in range(40):
        time.sleep(5)
        check = requests.get(
            f"https://graph.facebook.com/v18.0/{container_id}",
            params={'fields': 'status_code', 'access_token': token}
        )
        status = check.json().get('status_code', '')
        log.info(f"  Status: {status} ({(i+1)*5}s)")
        if status == 'FINISHED':
            break
        elif status == 'ERROR':
            log.error(f"Processing error: {check.json()}")
            return False

    if status != 'FINISHED':
        log.error("Processing timeout!")
        return False

    pub = requests.post(
        f"https://graph.facebook.com/v18.0/{biz_id}/media_publish",
        data={'creation_id': container_id, 'access_token': token}
    )

    if pub.status_code == 200:
        log.info("Instagram Reels published!")
        return True
    else:
        log.error(f"Publish error: {pub.text}")
        return False


def check_and_post():
    force_id = os.getenv("FORCE_VIDEO_ID")

    if force_id:
        log.info(f"FORCE MODE: {force_id}")
        new = [{"id": force_id, "title": force_id, "link": f"https://www.youtube.com/watch?v={force_id}", "description": ""}]
    else:
        new = get_new_videos(CHANNEL_ID)

    if not new:
        log.info("No new videos.")
        return

    log.info(f"Found {len(new)} new videos")

    for video in new:
        log.info(f"Processing: {video['title']}")

        video_path = download_video(video["link"])
        if not video_path:
            log.error(f"Download failed: {video['title']}")
            continue

        log.info("Uploading to catbox...")
        video_url = upload_to_catbox(video_path)
        try:
            os.remove(video_path)
            os.rmdir(os.path.dirname(video_path))
        except:
            pass

        if not video_url:
            log.error("Catbox upload failed!")
            continue

        caption = generate_caption(video["title"], video.get("description", ""))
        log.info(f"Caption: {caption[:100]}...")

        if not publish_to_instagram(video_url, caption):
            log.error(f"Instagram failed: {video['title']}")
            continue

        mark_posted(video["id"])
        log.info(f"Done: {video['title']}")


if __name__ == "__main__":
    import sys
    if "--run-once" in sys.argv:
        check_and_post()
        commit_posted()
    else:
        import schedule
        log.info("Bot started - checking every 10 minutes")
        schedule.every(10).minutes.do(check_and_post)
        check_and_post()
        while True:
            schedule.run_pending()
            time.sleep(60)
