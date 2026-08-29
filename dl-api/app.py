import os
import sys
import json
import tempfile
import subprocess
import logging

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


@app.route('/download', methods=['POST'])
def download():
    data = request.json
    video_url = data.get('url')
    quality = data.get('quality', '720')

    if not video_url:
        return jsonify({'error': 'No URL provided'}), 400

    tmp_dir = tempfile.mkdtemp()
    output_path = os.path.join(tmp_dir, 'video.mp4')

    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '-f', f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best',
        '--merge-output-format', 'mp4',
        '--cookies', COOKIES_PATH,
        '--remote-components', 'ejs:github',
        '--quiet',
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
        return jsonify({'error': 'Download timeout'}), 500

    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        logger.info(f'Success: {os.path.getsize(output_path)} bytes')
        return send_file(output_path, mimetype='video/mp4', as_attachment=True,
                         download_name='video.mp4')

    for f in os.listdir(tmp_dir):
        if f.endswith(('.mp4', '.webm', '.mkv')):
            found = os.path.join(tmp_dir, f)
            logger.info(f'Found: {found} ({os.path.getsize(found)} bytes)')
            return send_file(found, mimetype='video/mp4', as_attachment=True,
                             download_name='video.mp4')

    return jsonify({'error': 'Download failed', 'stderr': result.stderr[:500] if result.stderr else ''}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT', 8080))
    logger.info(f'Starting on port {port}, cookies: {COOKIES_PATH}')
    app.run(host='0.0.0.0', port=port)
