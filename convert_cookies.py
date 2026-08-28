import json

cookies = []
with open('cookies.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for line in lines:
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    
    parts = line.split('\t')
    if len(parts) < 7:
        continue
    
    domain = parts[0]
    name = parts[5]
    value = parts[6]
    path = parts[2]
    secure = parts[3].upper() == 'TRUE'
    httponly = parts[1].upper() == 'TRUE'
    
    if 'tiktok' in domain.lower():
        cookie = {
            'name': name,
            'value': value,
            'domain': domain,
            'path': path,
            'secure': secure,
            'httpOnly': httponly,
            'sameSite': 'None' if secure else 'Lax'
        }
        cookies.append(cookie)

print("Toplam TikTok cookie: " + str(len(cookies)))

with open('tiktok_cookies.json', 'w', encoding='utf-8') as f:
    json.dump(cookies, f, indent=2, ensure_ascii=False)

print('tiktok_cookies.json kaydedildi!')

for c in cookies[:5]:
    val_preview = c['value'][:30]
    print("  " + c['name'] + ": " + val_preview + "...")
