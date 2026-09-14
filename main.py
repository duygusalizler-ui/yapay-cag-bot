import os
import json
import requests
import google.generativeai as genai
import yt_dlp
import subprocess

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
        print(f"AI notice: {e}")

    temp_input = "temp_download.mp4"
    output_file = "final_reel.mp4"

    print("Downloading video using yt-dlp Python library...")
    ydl_opts = {
        'format': 'b',
        'outtmpl': temp_input,
        'extractor_args': {'youtube': {'player_client': ['android']}}
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])

    print(f"Cutting video from {start_sec}s for 30 seconds...")
    subprocess.run([
        "ffmpeg", "-y", "-ss", str(start_sec), "-i", temp_input, "-t", "30",
        "-vf", "scale=-2:1920,crop=1080:1920:(in_w-1080)/2:0",
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k", output_file
    ], check=True)

    if os.path.exists(temp_input):
        os.remove(temp_input)

    if telegram_token and telegram_chat_id:
        print("Sending to Telegram...")
        full_message = f"🚀 **Yapay Çağ - Yeni Reels Hazır!**\n\n{caption}\n\n{hashtags}\n\n🔗 **Kaynak:** {youtube_url}"
        with open(output_file, 'rb') as video_file:
            url = f"https://api.telegram.org/bot{telegram_token}/sendVideo"
            files = {'video': video_file}
            payload = {'chat_id': telegram_chat_id, 'caption': full_message, 'parse_mode': 'Markdown'}
            requests.post(url, data=payload, files=files)
        print("Sent successfully!")

if __name__ == "__main__":
    main()
