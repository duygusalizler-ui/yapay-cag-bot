import os
import subprocess
import json
import requests
import google.generativeai as genai

def extract_video_id(url):
    if "youtu.be" in url:
        return url.split("/")[-1].split("?")[0]
    elif "watch?v=" in url:
        return url.split("watch?v=")[1].split("&")[0]
    return "dQw4w9WgXcQ"

def main():
    youtube_url = os.environ.get("YOUTUBE_URL")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    if not youtube_url:
        print("YOUTUBE_URL is required.")
        return

    video_id = extract_video_id(youtube_url)
    print(f"Video ID: {video_id}")

    start_sec = 10
    caption = "Yapay zeka iş dünyasını ve meslekleri kökten değiştiriyor! Gelecekte seni ne bekliyor?"
    hashtags = "#YapayÇağ #YapayZeka #Gelecek #Teknoloji #Kariyer"

    try:
        genai.configure(api_key=gemini_api_key)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        prompt = f"""
        Bu YouTube videosu için:
        1. İzleyicinin dikkatini çekecek en vurucu 30 saniyelik kısmın başlangıç saniyesini (Sadece sayı, örn: 10) bul.
        2. Instagram Reels için dikkat çekici bir açıklama yaz.
        3. Uygun hashtag'ler belirle.
        
        Cevabını Kesinlikle şu JSON formatında ver, başka hiçbir şey yazma:
        {{
          "start_second": 10,
          "caption": "Açıklama buraya",
          "hashtags": "#etiket1 #etiket2"
        }}
        URL: {youtube_url}
        """
        
        print("Analyzing with Gemini AI...")
        response = model.generate_content(prompt)
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
            
        data = json.loads(text)
        start_sec = int(data.get("start_second", 10))
        caption = data.get("caption", caption)
        hashtags = data.get("hashtags", hashtags)
    except Exception as e:
        print(f"AI notice (using smart defaults): {e}")

    print(f"Start Second: {start_sec}")
    print(f"Caption: {caption}")

    temp_input = "temp_download.mp4"
    output_file = "final_reel.mp4"

    print("Downloading video via yt-dlp with android bypass...")
    subprocess.run([
        "yt-dlp",
        "--extractor-args", "youtube:player_client=android",
        "-f", "b",
        "-o", temp_input,
        youtube_url
    ], check=True)

    print(f"Cutting video from {start_sec}s for 30 seconds and formatting to 9:16...")
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_sec), "-i", temp_input, "-t", "30",
        "-vf", "scale=-2:1920,crop=1080:1920:(in_w-1080)/2:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k", output_file
    ], check=True)

    if os.path.exists(temp_input):
        os.remove(temp_input)

    if telegram_token and telegram_chat_id:
        print("Sending result to Telegram...")
        full_message = f"🚀 **Yapay Çağ - Yeni Reels Hazır!**\n\n{caption}\n\n{hashtags}\n\n🔗 **Kaynak:** {youtube_url}"
        
        with open(output_file, 'rb') as video_file:
            url = f"https://api.telegram.org/bot{telegram_token}/sendVideo"
            files = {'video': video_file}
            payload = {
                'chat_id': telegram_chat_id,
                'caption': full_message,
                'parse_mode': 'Markdown'
            }
            requests.post(url, data=payload, files=files)
        print("Successfully sent to Telegram!")
    else:
        print("Telegram credentials missing.")

if __name__ == "__main__":
    main()
