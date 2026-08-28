# YouTube to Instagram & TikTok Otomatik Paylaşıcı

YouTube kanalınızdaki yeni videoları otomatik olarak Instagram ve TikTok'ta paylaşır.

## Özellikler

- YouTube RSS feed ile yeni video takibi
- Instagram Reels olarak otomatik paylaşım
- TikTok'a YouTube linkinden otomatik yükleme
- Belirlenen saatlerde paylaşım
- GitHub Actions ile ücretsiz 7/24 çalışma
- Video başlık filtresi desteği

## Kurulum

### 1. GitHub Repository Oluştur

1. GitHub'da yeni repository oluştur
2. Bu dosyaları repository'ye yükle

### 2. YouTube API (Gerekmez)

YouTube RSS feed kullandığımız için API key gerekmez!

### 3. Instagram API

1. [Facebook Developer](https://developers.facebook.com/) hesap oluştur
2. Yeni uygulama oluştur (tür: "Business")
3. Graph API Explorer'dan izinleri ekle:
   - `instagram_basic`
   - `instagram_content_publish`
   - `pages_show_list`
   - `pages_read_engagement`
4. Access Token oluştur (uzun ömürlü token kullan)
5. Instagram Business hesabının ID'sini bul

### 4. TikTok API

1. [TikTok Developer](https://developers.tiktok.com/) hesap oluştur
2. Yeni uygulama oluştur
3. `video.upload` izni ekle
4. Access Token al

### 5. GitHub Secrets Ayarla

Repository Settings > Secrets and variables > Actions kısmına ekle:

| Secret Adı | Açıklama |
|------------|----------|
| `YOUTUBE_CHANNEL_ID` | `UCDxooL2M22LvKI32dREyjfQ` |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram API token |
| `INSTAGRAM_BUSINESS_ACCOUNT_ID` | Instagram business hesap ID |
| `TIKTOK_ACCESS_TOKEN` | TikTok API token |
| `POST_TIMES` | Paylaşım saatleri (örn: `09:00,14:00,19:00`) |
| `VIDEO_FILTER` | Video filtresi (örn: `konu1,konu2` veya boş) |

## Kullanım

### Otomatik (Önerilen)
GitHub Actions her saat başı yeni videoları kontrol eder.

### Manuel
```bash
pip install -r requirements.txt
cp .env.example .env
# .env dosyasını düzenle
python main.py
```

### Zamanlayıcı ile
```bash
python scheduler.py
```

## Paylaşım Zamanları

`POST_TIMES` secret'ını şu formatta ayarla:
```
09:00,14:00,19:00
```

Bu saatlerde yeni video varsa otomatik paylaşım yapılır.

## Dosya Yapısı

```
youtube-social-scheduler/
├── main.py                 # Ana script
├── scheduler.py            # Zamanlayıcı
├── requirements.txt        # Bağımlılıklar
├── .env.example            # Örnek env dosyası
├── .github/
│   └── workflows/
│       └── main.yml        # GitHub Actions
└── posted_videos.json      # Paylaşılan videolar (otomatik oluşur)
```

## Notlar

- RSS feed her videonun yayınlanmasından kısa süre sonra güncellenir
- Instagram Reels olarak paylaşılır
- TikTok'ta YouTube linkinden otomatik çekilir
- Aynı video tekrar paylaşılmaz (posted_videos.json ile takip)
