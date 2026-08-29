import os
import sys
import json
import tempfile
import subprocess
import logging
import requests as http_requests

sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

from flask import Flask, request, jsonify, send_file

app = Flask(__name__)

COOKIES_PATH = os.getenv('COOKIE_PATH', '/etc/secrets/cookies.txt')
if not os.path.exists(COOKIES_PATH):
    COOKIES_PATH = 'cookies.txt'


@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'cookies': os.path.exists(COOKIES_PATH)})


def _download_video(video_url, quality):
    tmp_dir = tempfile.mkdtemp()
    output_path = os.path.join(tmp_dir, 'video.mp4')

    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '-f', f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best',
        '--merge-output-format', 'mp4',
        '--cookies', COOKIES_PATH,
        '--no-playlist',
        '--no-progress',
        '--socket-timeout', '30',
        '-o', output_path,
        video_url
    ]

    logger.info(f'Downloading: {video_url} (quality: {quality})')
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        logger.info(f'yt-dlp exit code: {result.returncode}')
        if result.stderr:
            logger.info(f'stderr: {result.stderr[:300]}')
    except subprocess.TimeoutExpired:
        return None

    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        logger.info(f'Downloaded: {os.path.getsize(output_path)} bytes')
        return output_path

    for f in os.listdir(tmp_dir):
        if f.endswith(('.mp4', '.webm', '.mkv')):
            found = os.path.join(tmp_dir, f)
            logger.info(f'Found: {found} ({os.path.getsize(found)} bytes)')
            return found

    return None


def _upload_catbox(file_path):
    with open(file_path, 'rb') as f:
        resp = http_requests.post(
            'https://catbox.moe/user/api.php',
            data={'reqtype': 'fileupload', 'userhash': ''},
            files={'fileToUpload': ('video.mp4', f, 'video/mp4')},
            timeout=180
        )
    logger.info(f'Catbox: {resp.status_code} {resp.text[:200]}')
    if resp.status_code == 200 and resp.text.startswith('http'):
        return resp.text.strip()
    return None


@app.route('/download', methods=['POST'])
def download():
    data = request.json
    video_url = data.get('url')
    quality = data.get('quality', '720')

    if not video_url:
        return jsonify({'error': 'No URL provided'}), 400

    output_path = _download_video(video_url, quality)
    if output_path:
        return send_file(output_path, mimetype='video/mp4', as_attachment=True,
                         download_name='video.mp4')
    return jsonify({'error': 'Download failed'}), 500


@app.route('/download-upload', methods=['POST'])
def download_upload():
    data = request.json
    video_url = data.get('url')
    quality = data.get('quality', '720')

    if not video_url:
        return jsonify({'error': 'No URL provided'}), 400

    output_path = _download_video(video_url, quality)
    if not output_path:
        return jsonify({'error': 'Download failed'}), 500

    catbox_url = _upload_catbox(output_path)

    try:
        os.remove(output_path)
        os.rmdir(os.path.dirname(output_path))
    except:
        pass

    if catbox_url:
        return jsonify({'url': catbox_url})
    return jsonify({'error': 'Upload to catbox failed'}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    logger.info(f'Starting on port {port}, cookies: {COOKIES_PATH}')
    app.run(host='0.0.0.0', port=port)
