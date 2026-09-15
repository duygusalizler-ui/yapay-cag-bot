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

    response = None
    max_api_retries = 3
    for attempt in range(1, max_api_retries + 1):
        try:
            print(f"🔄 Ssemble API'ye bağlanılıyor (Deneme {attempt}/{max_api_retries})...")
            response = requests.post(create_url, json=payload, headers=headers, timeout=45)
            if response.status_code in [200, 201]:
                break
            else:
                print(f"Uyarı: API kodu {response.status_code}, yanıt: {response.text}")
        except Exception as e:
            print(f"Bağlantı hatası: {e}")
        time.sleep(5)

    if not response or response.status_code not in [200, 201]:
        print(f"❌ Ssemble API 3 denemede de yanıt vermedi! İşlem durduruluyor.")
        sys.exit(1)

    res_data = response.json()
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
    max_retries = 80
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
            print(f"Durum sorgulama sırasında geçici ağ hatası: {e}")

    if not completed:
        print("❌ Zaman Aşımı: Ssemble 20 dakika içinde videoyu tamamlayamadı.")
        sys.exit(1)

    print("🎯 Video başarıyla tamamlandı, 80+ viral skorlu elit klipler seçiliyor...")
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

    # SADECE 80 ve üzeri skorlu olanları filtrele ve büyükten küçüğe sırala
    filtered_clips = [
        c for c in clips 
        if float(c.get("viralScore") or c.get("score") or 0) >= 80
    ]
    
    top_clips = sorted(filtered_clips, key=lambda c: float(c.get("viralScore") or c.get("score") or 0), reverse=True)

    if not top_clips:
        print("⚠️ Bu videoda 80+ skorlu klip bulunamadı, en yüksek skorlu en iyi klip seçiliyor...")
        best_fallback = max(clips, key=lambda c: float(c.get("viralScore") or c.get("score") or 0))
        top_clips = [best_fallback]
    else:
        print(f"🔥 Toplam {len(clips)} klip arasından 80+ kriterine uyan {len(top_clips)} adet elit klip seçildi stok için gönderiliyor.")

    for index, clip in enumerate(top_clips, start=1):
        video_download_url = clip.get("videoUrl") or clip.get("url") or clip.get("downloadUrl")
        title = clip.get("title") or f"Yapay Zeka Trendleri #{index}"
        description = clip.get("description") or "Yapay zeka dünyasından öne çıkan çarpıcı anlar."
        hashtags = clip.get("hashtags") or "#YapayZeka #Teknoloji #Gelecek #Reels"
        score = clip.get("viralScore") or clip.get("score") or "N/A"

        if not video_download_url:
            print(f"Uyarı: {index}. klip için indirme linki bulunamadı, atlanıyor.")
            continue

        print(f"📥 [{index}/{len(top_clips)}] Nolu 80+ elit klip indiriliyor (Skor: {score})...")
        output_filename = f"final_reel_{index}.mp4"
        
        vid_res = requests.get(video_download_url, stream=True, timeout=120)
        with open(output_filename, "wb") as f:
            for chunk in vid_res.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        file_size = os.path.getsize(output_filename)
        if file_size < 5000:
            print(f"❌ Uyarı: {index}. klip dosyası çok küçük, atlanıyor.")
            continue

        if telegram_token and telegram_chat_id:
            print(f"📤 [{index}/{len(top_clips)}] Nolu klip Telegram kanalına gönderiliyor...")
            tg_url = f"https://api.telegram.org/bot{telegram_token}/sendVideo"
            
            full_message = (
                f"🚀 **Yapay Çağ - Elit Stok Seri (#{index})**\n\n"
                f"🔥 **Viral Skor:** {score}/100\n"
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
                tg_res = requests.post(tg_url, data=payload, files=files, timeout=120)
                if tg_res.status_code == 200:
                    print(f"✨ [{index}/{len(top_clips)}] Nolu klip kusursuz iletildi.")
                else:
                    print(f"Telegram gönderim hatası: {tg_res.text}")

        if os.path.exists(output_filename):
            os.remove(output_filename)
        
        time.sleep(3)

    print("🎯 80+ elit stok klipler başarıyla işlendi ve gönderildi!")

if __name__ == "__main__":
    main()
