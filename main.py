import os
import subprocess
import json
import requests
from youtube_transcript_api import YouTubeTranscriptApi
import google.generativeai as genai

def extract_video_id(url):
    if "youtu.be" in url:
        return url.split("/")[-1].split("?")[0]
    elif "watch?v=" in url:
        return url.split("watch?v=")[1].split("&")[0]
    return None

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

    transcript_text = ""
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['tr', 'en'])
        transcript_text = "\n".join([f"[{item['start']}] {item['text']}" for item in transcript_list])
    except Exception as e:
        print(f"Transcript could not be fetched: {e}. Defaulting to start=0.")
        transcript_text = "No transcript available."

    genai.configure(api_key=gemini_api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Aşağıda bir YouTube videosunun zaman damgalı transkripti bulunmaktadır. Bu metni analiz ederek:
    1. İzleyicinin dikkatini en çok çekecek, tartışma yaratacak veya en vurucu olan yaklaşık 30 saniyelik bir kesitin başlangıç saniyesini (Sadece saniye cinsinden sayı, örn: 45) bul.
    2. Instagram Reels için bu kesite uygun, dikkat çekici, merak uyandıran bir açıklama yaz.
    3. Uygun niş hashtag'leri belirle.

    Transkript:
    {transcript_text[:15000]}

    Cevabını Kesinlikle şu JSON formatında ver, başka hiçbir şey yazma:
    {{
      "start_second": 0,
      "caption": "Açıklama buraya",
      "hashtags": "#etiket1 #etiket2"
    }}
    """

    print("Analyzing video content with Gemini AI...")
    response = model.generate_content(prompt)
    ai_response_text = response.text.strip()
    if ai_response_text.startswith("```json"):
        ai_response_text = ai_response_text[7:-3].strip()
    elif ai_response_text.startswith("```"):
        ai_response_text = ai_response_text[3:-3].strip()

    data = json.loads(ai_response_text)
    start_sec = int(data.get("start_second", 0))
    caption = data.get("caption", "")
    hashtags = data.get("hashtags", "")

    print(f"AI Selected Start Second: {start_sec}")
    print(f"Generated Caption: {caption}")

    temp_input = "temp_download.mp4"
    output_file = "final_reel.mp4"

    print("Downloading video...")
    subprocess.run([
        "yt-dlp", "-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--merge-output-format", "mp4", "-o", temp_input, youtube_url
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
        full_message = f"🚀 **Yeni Reels Hazır!**\n\n{caption}\n\n{hashtags}\n\n🔗 **Kaynak:** {youtube_url}"
        
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
