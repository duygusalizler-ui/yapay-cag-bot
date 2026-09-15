import os
import sys
import time
import requests

def main():
    youtube_url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("YOUTUBE_URL")
    ssemble_api_key = os.getenv("SSEMBLE_API_KEY")
    template_id = os.getenv("SSEMBLE_TEMPLATE_ID")  # Ssemble marka şablon ID'niz
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not youtube_url:
        print("Hata: YouTube URL bulunamadı!")
        sys.exit(1)

    if not ssemble_api_key:
        print("Hata: SSEMBLE_API_KEY bulunamadı!")
        sys.exit(1)

    print(f"Ssemble API üzerinden video işleme başlatılıyor: {youtube_url}")

    # Ssemble üzerinden video kesme ve markalama isteği oluşturma
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
    
    if template_id:
        payload["templateId"] = template_id

    response = requests.post(create_url, json=payload, headers=headers)
    if response.status_code not in [200, 201]:
        print(f"Ssemble İstek Hatası: {response.status_code} - {response.text}")
        sys.exit(1)

    res_data = response.json()
    request_id = res_data.get("requestId") or res_data.get("request_id") or res_data.get("id")
    
    if not request_id:
        print(f"Hata: Ssemble'dan Request ID alınamadı! Yanıt: {res_data}")
        sys.exit(1)

    print(f"İşlem sıraya alındı. Request ID: {request_id}. Bulutta işlenmesi bekleniyor...")

    # İşlem durumunu sorgulama (Polling)
    status_url = f"https://aiclipping.ssemble.com/api/v1/shorts/{request_id}/status"
    max_retries = 40  # Yaklaşık 10 dakika maksimum bekleme süresi
    completed = False
    
    for i in range(max_retries):
        time.sleep(15)
        status_res = requests.get(status_url, headers={"X-API-Key": ssemble_api_key})
        if status_res.status_code == 200:
            status_data = status_res.json()
            status = status_data.get("status") or status_data.get("data", {}).get("status")
            print(f"Bulut işlem durumu: {status}")
            
            if status == "completed":
                completed = True
                break
            elif status == "failed":
                print("Ssemble video işleme başarısız oldu!")
                sys.exit(1)
        else:
            print(f"Durum kontrol uyarısı: {status_res.status_code}")

    if not completed:
        print("Zaman aşımı: Ssemble video işlemesi çok uzun sürdü.")
        sys.exit(1)

    # Sonuçları ve AI tarafından üretilen başlık/açıklama/hashtag'leri çekme
    print("Video başarıyla tamamlandı, detaylar alınıyor...")
    result_url = f"https://aiclipping.ssemble.com/api/v1/shorts/{request_id}"
    result_res = requests.get(result_url, headers={"X-API-Key": ssemble_api_key})
    
    if result_res.status_code != 200:
        print(f"Sonuçlar alınamadı: {result_res.status_code}")
        sys.exit(1)

    result_data = result_res.json()
    clips = result_data.get("clips") or result_data.get("data", {}).get("clips") or [result_data]
    
    if not clips:
        print("Hata: Üretilen video klip bilgisi bulunamadı!")
        sys.exit(1)

    first_clip = clips[0]
    video_download_url = first_clip.get("videoUrl") or first_clip.get("url") or first_clip.get("downloadUrl")
    title = first_clip.get("title") or "Yapay Zeka ve Gelecek"
    description = first_clip.get("description") or "Yapay zeka dünyayı ve meslekleri dönüştürmeye devam ediyor."
    hashtags = first_clip.get("hashtags") or "#YapayZeka #Teknoloji #Gelecek #Reels"

    if not video_download_url:
        print("Hata: Video indirme bağlantısı bulunamadı!")
        sys.exit(1)

    print(f"Video indiriliyor: {video_download_url}")
    vid_res = requests.get(video_download_url)
    output_filename = "final_reel.mp4"
    with open(output_filename, "wb") as f:
        f.write(vid_res.content)

    # Telegram'a konuyla ilgili açıklama, hashtag ve video ile birlikte gönderme
    if telegram_token and telegram_chat_id:
        print("Telegram'a gönderiliyor...")
        tg_url = f"https://api.telegram.org/bot{telegram_token}/sendVideo"
        
        full_message = f"🚀 **Yapay Çağ - Ssemble Otomasyonu**\n\n📌 **Başlık:** {title}\n\n📝 {description}\n\n🏷 {hashtags}\n\n🔗 **Kaynak:** {youtube_url}"
        
        with open(output_filename, 'rb') as video_file:
            files = {'video': video_file}
            payload = {
                'chat_id': telegram_chat_id,
                'caption': full_message,
                'parse_mode': 'Markdown'
            }
            tg_res = requests.post(tg_url, data=payload, files=files)
            if tg_res.status_code == 200:
                print("İşlem tamam! Video Telegram kanalına başarıyla iletildi.")
            else:
                print(f"Telegram gönderim hatası: {tg_res.text}")

    # Geçici dosyayı temizleme
    if os.path.exists(output_filename):
        os.remove(output_filename)

if __name__ == "__main__":
    main()
