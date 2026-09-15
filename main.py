import os
import sys
import time
import requests

def run_bot():
    youtube_url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("YOUTUBE_URL")
    ssemble_api_key = os.getenv("SSEMBLE_API_KEY")
    template_id = os.getenv("SSEMBLE_TEMPLATE_ID")
    telegram_token = os.getenv("TELEGRAM_TOKEN")
    telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not youtube_url:
        print("Hata: YouTube URL bulunamadı!")
        return False

    if not ssemble_api_key:
        print("Hata: SSEMBLE_API_KEY GitHub Secrets'ta tanımlı değil!")
        return False

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
    for attempt in range(1, 4):
        try:
            print(f"🔄 Ssemble API'ye bağlanılıyor (Deneme {attempt}/3)...")
            response = requests.post(create_url, json=payload, headers=headers, timeout=45)
            if response.status_code in [200, 201]:
                break
            else:
                print(f"Uyarı: API kodu {response.status_code}, yanıt: {response.text}")
        except Exception as e:
            print(f"Bağlantı hatası: {e}")
        time.sleep(5)

    if not response or response.status_code not in [200, 201]:
        print("❌ Ssemble API yanıt vermedi, bu tur atlanıyor.")
        return False

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
        print(f"Hata: Request ID dönmedi! Gelen Yanıt: {res_data}")
        return False

    print(f"✅ İşlem sıraya alındı. Request ID: {request_id}. Yapay zeka işliyor...")

    status_url = f"https://aiclipping.ssemble.com/api/v1/shorts/{request_id}/status"
    completed = False
    
    for attempt in range(1, 81):
        time.sleep(15)
        try:
            status_res = requests.get(status_url, headers={"X-API-Key": ssemble_api_key}, timeout=20)
            if status_res.status_code == 200:
                status_data = status_res.json()
                status_content = status_data.get("data", {}) if isinstance(status_data.get("data"), dict) else {}
                status = status_data.get("status") or status_content.get("status")
                print(f"[{attempt}/80] İşlem durumu: {status}")
                
                if status == "completed":
                    completed = True
                    break
                elif status == "failed":
                    print("❌ Ssemble tarafında işlem başarısız oldu!")
                    return False
        except Exception as e:
            print(f"Durum sorgulama hatası: {e}")

    if not completed:
        print("❌ Zaman aşımı: İşlem tamamlanamadı.")
        return False

    print("🎯 İşlem tamamlandı, klipler alınıyor...")
    result_url = f"https://aiclipping.ssemble.com/api/v1/shorts/{request_id}"
    
    try:
        result_res = requests.get(result_url, headers={"X-API-Key": ssemble_api_key}, timeout=30)
        if result_res.status_code != 200:
            print(f"Sonuç alınamadı kod: {result_res.status_code}")
            return False
        result_data = result_res.json()
    except Exception as e:
        print(f"Sonuçlar alınırken hata: {e}")
        return False

    res_clips_container = result_data.get("clips") or result_data.get("data", {}).get("clips") or result_data.get("data")
    if isinstance(res_clips_container, dict):
        clips = res_clips_container.get("clips", [res_clips_container])
    elif isinstance(res_clips_container, list):
        clips = res_clips_container
    else:
        clips = [result_data]

    if not clips:
        print(f"Hata: Klip listesi boş. Gelen veri: {result_data}")
        return False

    # Resmi Ssemble alanı olan 'viral_score' üzerinden büyükten küçüğe sıralama
    sorted_clips = sorted(clips, key=lambda c: float(c.get("viral_score") or c.get("viralityScore") or c.get("score") or 0), reverse=True)

    success_sent = False
    for index, clip in enumerate(sorted_clips[:5], start=1):
        # RESMİ SSEMBLE API ALANI: video_url
        video_download_url = clip.get("video_url") or clip.get("videoUrl") or clip.get("url")
        title = clip.get("title") or "Yapay Zeka Trendleri"
        description = clip.get("description") or "Yapay zeka dünyasından öne çıkan çarpıcı anlar."
        hashtags = clip.get("hashtags") or "#YapayZeka #Teknoloji #Gelecek #Reels"
        score = clip.get("viral_score") or clip.get("viralityScore") or clip.get("score") or "80+"

        if not video_download_url or "youtube.com" in video_download_url or "youtu.be" in video_download_url:
            print(f"⚠️ {index}. klip için geçerli render edilmiş video URL'si bulunamadı (Atlanıyor).")
            continue

        print(f"📥 {index}. klip indiriliyor... URL: {video_download_url}")
        output_filename = f"final_reel_{index}.mp4"
        
        try:
            vid_res = requests.get(video_download_url, stream=True, timeout=120)
            with open(output_filename, "wb") as f:
                for chunk in vid_res.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)

            # Dosya bütünlük kontrolü (MP4 / WebM imzası)
            with open(output_filename, "rb") as f:
                header = f.read(200)
                if b'ftyp' not in header and b'moov' not in header and b'mdat' not in header and b'webm' not in header:
                    text_preview = header.decode('utf-8', errors='ignore')
                    print(f"❌ HATA: İndirilen dosya geçerli bir video değil! İçerik: {text_preview}")
                    if os.path.exists(output_filename):
                        os.remove(output_filename)
                    continue

            # Telegram'a Gönder
            if telegram_token and telegram_chat_id:
                print(f"📤 {index}. klip Telegram'a gönderiliyor...")
                tg_url = f"https://api.telegram.org/bot{telegram_token}/sendVideo"
                full_message = (
                    f"🚀 **Yapay Çağ - Elit Stok**\n\n"
                    f"🔥 **Viral Skor:** {score}/100\n"
                    f"📌 **Başlık:** {title}\n\n"
                    f"📝 {description}\n\n"
                    f"🏷 {hashtags}"
                )
                
                with open(output_filename, 'rb') as video_file:
                    tg_res = requests.post(tg_url, data={'chat_id': telegram_chat_id, 'caption': full_message, 'parse_mode': 'Markdown'}, files={'video': video_file}, timeout=120)
                    if tg_res.status_code == 200:
                        print("✨ Klip başarıyla iletildi!")
                        success_sent = True
                    else:
                        print(f"Telegram hata: {tg_res.text}")

            if os.path.exists(output_filename):
                os.remove(output_filename)
            
            if success_sent:
                break

        except Exception as e:
            print(f"İndirme/gönderim istisnası: {e}")
            if os.path.exists(output_filename):
                os.remove(output_filename)

    return success_sent

if __name__ == "__main__":
    for global_attempt in range(1, 4):
        print(f"\n🔄 Otomasyon Döngüsü Başlatılıyor (Global Deneme {global_attempt}/3)...")
        if run_bot():
            print("✨ İşlem kusursuz tamamlandı!")
            sys.exit(0)
        else:
            print(f"⚠️ Bu turda aksaklık oldu, 10 saniye sonra tekrar deneniyor...")
            time.sleep(10)
    
    print("❌ 3 global denemede de sonuç alınamadı.")
    sys.exit(1)
