import os
import json
import tempfile
import subprocess
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


def download_video(url):
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
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--cookies", cookie_path,
        "--js-runtimes", "node",
        "--no-playlist",
        "--no-progress",
        "--socket-timeout", "30",
        "-o", out,
        url
    ]

    log.info(f"Downloading: {url}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    log.info(f"yt-dlp exit: {r.returncode}")
    if r.stderr:
        log.info(f"stderr: {r.stderr[:500]}")

    if os.path.exists(out) and os.path.getsize(out) > 100000:
        return out

    for f in os.listdir(tmp):
        if f.endswith((".mp4", ".webm", ".mkv")):
            return os.path.join(tmp, f)

    return None


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


def upload_to_instagram(video_path, caption):
    from instagrapi import Client

    cl = Client()
    cl.login(os.getenv("INSTAGRAM_USERNAME"), os.getenv("INSTAGRAM_PASSWORD"))

    media = cl.clip_upload(path=video_path, caption=caption)
    log.info(f"Instagram upload success! Media ID: {media.pk}")
    return True


def check_and_post():
    force_id = os.getenv("FORCE_VIDEO_ID")

    if force_id:
        log.info(f"FORCE MODE: posting {force_id}")
        videos = get_feed(CHANNEL_ID)
        new = [v for v in videos if v["id"] == force_id]
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

        caption = generate_caption(video["title"], video.get("description", ""))
        log.info(f"Caption: {caption[:100]}...")

        try:
            upload_to_instagram(video_path, caption)
        except Exception as e:
            log.error(f"Instagram upload failed: {e}")
            continue
        finally:
            try:
                os.remove(video_path)
                os.rmdir(os.path.dirname(video_path))
            except:
                pass

        mark_posted(video["id"])
        log.info(f"Done: {video['title']}")


if __name__ == "__main__":
    check_and_post()
    commit_posted()
