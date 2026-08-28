import os
import schedule
import time
import logging
from dotenv import load_dotenv
from main import check_and_post

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_schedule():
    post_times_str = os.getenv('POST_TIMES', '09:00,14:00,19:00')
    post_times = [t.strip() for t in post_times_str.split(',')]

    for post_time in post_times:
        schedule.every().day.at(post_time).do(check_and_post)
        logger.info(f"Paylaşım zamanı eklendi: {post_time}")

    logger.info(f"Toplam {len(post_times)} zamanlama aktif")


def run_scheduler():
    setup_schedule()
    logger.info("Zamanlayıcı başlatıldı. Ctrl+C ile durdurun.")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    run_scheduler()
