import os
import json
import time
import logging
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

COOKIES_FILE = Path("tiktok_cookies.json")


async def save_tiktok_cookies():
    logger.info("TikTok'a giriş yapın... Tarayıcı açılacak.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto("https://www.tiktok.com/login")
        
        logger.info("Giriş yaptıktan sonra 'Enter' tuşuna basın...")
        await asyncio.get_event_loop().run_in_executor(None, input)
        
        cookies = await context.cookies()
        
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f, indent=2)
        
        logger.info(f"Cookie'ler kaydedildi: {COOKIES_FILE}")
        
        await browser.close()


async def upload_to_tiktok(video_path, caption, hashtags=None):
    if not COOKIES_FILE.exists():
        logger.error("TikTok cookie'leri bulunamadi! Once tiktok_login.py calistirin.")
        return False
    
    with open(COOKIES_FILE, 'r') as f:
        cookies = json.load(f)
    
    full_caption = caption
    if hashtags:
        hashtag_str = " ".join([f"#{h}" for h in hashtags])
        full_caption = f"{caption}\n\n{hashtag_str}"
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        await context.add_cookies(cookies)
        page = await context.new_page()
        
        await page.goto("https://www.tiktok.com/creator#/upload?scene=creator_center")
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        if "login" in page.url.lower():
            logger.error("Cookie'ler suresi dolmus! Tekrar giris yapin.")
            await browser.close()
            return False
        
        try:
            upload_input = page.locator('input[type="file"][accept*="video"]')
            await upload_input.set_input_files(video_path)
            logger.info("Video yuklendi, bekleniyor...")
            
            await asyncio.sleep(10)
            
            caption_box = page.locator('[contenteditable="true"]').first
            await caption_box.click()
            await caption_box.fill(full_caption)
            logger.info("Caption yazildi.")
            
            await asyncio.sleep(2)
            
            post_btn = page.locator('button:has-text("Post")').first
            await post_btn.click()
            logger.info("Paylas butonuna basildi...")
            
            await asyncio.sleep(10)
            
            logger.info("TikTok video basariyla paylasildi!")
            await browser.close()
            return True
            
        except Exception as e:
            logger.error(f"TikTok yukleme hatasi: {e}")
            await browser.close()
            return False


if __name__ == "__main__":
    asyncio.run(save_tiktok_cookies())
