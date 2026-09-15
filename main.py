import os
import sys
import time
import requests

def main():
    youtube_url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("YOUTUBE_URL")
    ssemble_api_key = os.getenv("SSEMBLE_API_KEY")
    template_id = os.getenv("SSEMBLE_TEMPLATE_ID")
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not youtube_url:
        print("Hata: YouTube URL bulunamadı!")
        sys.exit(1)

    if not ssemble_api_key:
        print("Hata: SSEMBLE_API_KEY GitHub Secrets'ta tanımlı değil!")
        sys.exit(1)

    print(f"🚀 Ssemble API isteği başlatılıyor. Hedef URL: {youtube_url}")

    create_url = "https://aiclipping.ssemble.com/api/v1/shorts/create"
    headers = {
        "X-API-Key": ssemble_api_key,
        "Content-Type": "application/json"
    }
    payload = {
        "url": youtube_url,
        "preferredLength": "under60sec",
        "language": "tr"
    }
    
    if template_id and template_id.strip():
        payload["templateId"] = template_id.strip()

    try:
        response = requests.post(create_url, json=payload, headers=headers, timeout=30)
    except Exception as e:
        print(f"Bağlantı Hatası (Ssemble Create): {e}")
        sys.exit(1)

    if response.status_code not in [200, 201]:
        print(f"Ssemble API Reddeti! Kod: {response.status_code} - Yanıt: {response.text}")
        sys.exit(1)

    res_data = response.json()
    request_id = res_data.get("requestId") or res_data.get("request_id") or res_data.get("id")
    
    if not request_id:
        print(f"Hata: Ssemble'dan geçerli bir Request ID dönmedi! Gelen Yanıt: {res_data}")
        sys.exit(1)

    print(f"✅ İşlem sıraya alındı. Request ID: {request_id}. Bulutta işlenmesi bekleniyor...")

    status_url = f"https://aiclipping.ssemble.com/api/v1/shorts/{request_id}/status"
    max_retries = 40
    completed = False
    
    for attempt in range(1, max_retries + 1):
        time.sleep(15)
        try:
            status_res = requests.get(status_url, headers={"X-API-Key": ssemble_api_key}, timeout=20)
            if status_res.status_code == 200:
                status_data = status_res.json()
                status = status_data.get("status") or status_data.get("data", {}).get("status")
                print(f"[{attempt}/{max_retries}] Bulut işlem durumu: {status}")
                
                if status == "completed":
                    completed = True
                    break
                elif status == "failed":
                    print("❌ Ssemble bulut sunucusunda video işleme başarısız oldu!")
                    sys.exit(1)
            else:
                print(f"Uyarı: Durum kodu {status_res.status_code}, tekrar deneniyor...")
        except Exception as e:
            print(f"Durum sorgulama sırasında hata oluştu: {e}")

    if not completed:
        print("❌ Zaman Aşımı: Ssemble 10 dakika içinde videoyu tamamlayamadı.")
        sys.exit(1)

    print("🎯 Video başarıyla tamamlandı, detaylar ve indirme bağlantısı alınıyor...")
    result_url = f"https://aiclipping.ssemble.com/api/v1/shorts/{request_id}"
    
    try:
        result_res = requests.get(result_url, headers={"X-API-Key": ssemble_api_key}, timeout=30)
    except Exception as e:
        print(f"Sonuçlar alınırken hata: {e}")
        sys.exit(1)
        
    if result_res.status_code != 200:
        print(f"Sonuç verisi çekilemedi. Kod: {result_res.status_code}")
        sys.exit(1)

    result_data = result_res.json()
    clips = result_data.get("clips") or result_data.get("data", {}).get("clips")
    
    if not clips and isinstance(result_data, dict):
        clips = [result_data]

    if not clips:
        print(f"Hata: Üretilen klip bilgisine ulaşılamadı. Gelen veri: {result_data}")
        sys.exit(1)

    first_clip = clips[0]
    video_download_url = first_clip.get("videoUrl") or first_clip.get("url") or first_clip.get("downloadUrl")
    title = first_clip.get("title") or "Yapay Zeka ve Gelecek Trendleri"
    description = first_clip.get("description") or "Yapay zeka iş dünyasını ve meslekleri kökten dönüştürmeye devam ediyor."
    hashtags = first_clip.get("hashtags") or "#YapayZeka #Teknoloji #Gelecek #Reels"

    if not video_download_url:
        print(f"Hata: Video indirme linki bulunamadı! Klip verisi: {first_clip}")
        sys.exit(1)

    print(f"📥 Markalanmış video indiriliyor...")
    vid_res = requests.get(video_download_url, timeout=60)
    output_filename = "final_reel.mp4"
    with open(output_filename, "wb") as f:
        f.write(vid_res.content)

    if telegram_token and telegram_chat_id:
        print("📤 Telegram kanalına gönderiliyor...")
        tg_url = f"https://api.telegram.org/bot{telegram_token}/sendVideo"
        
        full_message = (
            f"🚀 **Yapay Çağ - Otomatik Viral Stüdyo**\n\n"
            f"📌 **Başlık:** {title}\n\n"
            f"📝 {description}\n\n"
            f"🏷 {hashtags}\n\n"
            f"🔗 **Kaynak:** {youtube_url}"
        )
        
        with open(output_filename, 'rb') as video_file:
            files = {'video': video_file}
            payload = {
                'chat_id': telegram_chat_id,
                'caption': full_message,
                'parse_mode': 'Markdown'
            }
            tg_res = requests.post(tg_url, data=payload, files=files, timeout=60)
            if tg_res.status_code == 200:
                print("✨ Harika! Video ve açıklamalarıyla birlikte Telegram'a başarıyla iletildi.")
            else:
                print(f"Telegram gönderim hatası: {tg_res.text}")

    if os.path.exists(output_filename):
        os.remove(output_filename)

if __name__ == "__main__":
    main()
