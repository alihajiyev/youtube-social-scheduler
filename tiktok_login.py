import json
import asyncio
from playwright.async_api import async_playwright


async def save_tiktok_cookies():
    print("Tarayici aciliyor...")
    print("TikTok'a giris yapin, giris yapinca tarayiciyi KAPATMAYIN.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto("https://www.tiktok.com/login")
        
        print("Giris yapmaniz bekleniyor...")
        
        while True:
            cookies = await context.cookies()
            tiktok_cookies = [c for c in cookies if "tiktok" in c.get("domain", "")]
            
            logged_in = any("sessionid" in c.get("name", "") or "passport_csrf_token" in c.get("name", "") for c in tiktok_cookies)
            
            if logged_in:
                print(f"Giris tespit edildi! {len(tiktok_cookies)} cookie kaydediliyor...")
                
                with open("tiktok_cookies.json", "w") as f:
                    json.dump(tiktok_cookies, f, indent=2)
                
                print("Basarili! Tiktok cookies.json kaydedildi.")
                break
            
            await asyncio.sleep(2)
        
        await browser.close()


if __name__ == "__main__":
    asyncio.run(save_tiktok_cookies())
