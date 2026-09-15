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

    print(f"🚀 Ssemble API viral tarama başlatılıyor. Hedef URL: {youtube_url}")

    create_url = "https://aiclipping.ssemble.com/api/v1/shorts/create"
    headers = {
        "X-API-Key": ssemble_api_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "url": youtube_url,
        "start": 0,
        "end": 1200,
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
        print(f"Ssemble API Reddetti! Kod: {response.status_code} - Yanıt: {response.text}")
        sys.exit(1)

    res_data = response.json()
    
    # Gelen yanıtın 'data' içinde olup olmadığını kontrol eden güvenli yapı
    data_field = res_data.get("data", {}) if isinstance(res_data.get("data"), dict) else {}
    request_id = (
        res_data.get("requestId") or 
        res_data.get("request_id") or 
        res_data.get("id") or 
        data_field.get("requestId") or 
        data_field.get("request_id") or 
        data_field.get("id")
    )
    
    if not request_id:
        print(f"Hata: Ssemble'dan geçerli bir Request ID dönmedi! Gelen Yanıt: {res_data}")
        sys.exit(1)

    print(f"✅ İşlem sıraya alındı. Request ID: {request_id}. Yapay zeka en viral anları işliyor...")

    status_url = f"https://aiclipping.ssemble.com/api/v1/shorts/{request_id}/status"
    max_retries = 40
    completed = False
    
    for attempt in range(1, max_retries + 1):
        time.sleep(15)
        try:
            status_res = requests.get(status_url, headers={"X-API-Key": ssemble_api_key}, timeout=20)
            if status_res.status_code == 200:
                status_data = status_res.json()
                status_content = status_data.get("data", {}) if isinstance(status_data.get("data"), dict) else {}
                status = status_data.get("status") or status_content.get("status")
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

    print("🎯 Video başarıyla tamamlandı, en yüksek viral skorlu klip seçiliyor...")
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
    res_clips_container = result_data.get("clips") or result_data.get("data", {}).get("clips") or result_data.get("data")
    
    if isinstance(res_clips_container, dict):
        clips = res_clips_container.get("clips", [res_clips_container])
    elif isinstance(res_clips_container, list):
        clips = res_clips_container
    else:
        clips = [result_data]

    if not clips:
        print(f"Hata: Üretilen klip bilgisine ulaşılamadı. Gelen veri: {result_data}")
        sys.exit(1)

    best_clip = max(clips, key=lambda c: c.get("viralScore") or c.get("score") or 0) if len(clips) > 0 else clips[0]

    video_download_url = best_clip.get("videoUrl") or best_clip.get("url") or best_clip.get("downloadUrl")
    title = best_clip.get("title") or "Yapay Zeka ve Gelecek Trendleri"
    description = best_clip.get("description") or "Yapay zeka iş dünyasını ve meslekleri kökten dönüştürmeye devam ediyor."
    hashtags = best_clip.get("hashtags") or "#YapayZeka #Teknoloji #Gelecek #Reels"

    if not video_download_url:
        print(f"Hata: Video indirme linki bulunamadı! Klip verisi: {best_clip}")
        sys.exit(1)

    print(f"📥 En viral klip indiriliyor...")
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
                print("✨ Harika! En viral klip ve açıklamalarıyla birlikte Telegram'a başarıyla iletildi.")
            else:
                print(f"Telegram gönderim hatası: {tg_res.text}")

    if os.path.exists(output_filename):
        os.remove(output_filename)

if __name__ == "__main__":
    main()
