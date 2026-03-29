import os
import requests
import pickle
import warnings
# Warnings ko hide karne ke liye
warnings.filterwarnings("ignore")

# Nayi Libraries ka sahi import (Phone friendly)
from google import genai
from moviepy import VideoFileClip, AudioFileClip, vfx
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow

# ================= CONFIG (Apni keys yahan bharein) =================
TELEGRAM_TOKEN = "8080221095:AAFnsPW-6FvmUUZk2IGutf_tQFlo-CI5wdE"
GEMINI_API_KEY = "AIzaSyDo0LeUPiMrGDCttuQmvmMYkJJiLi1kdr8" 
PEXELS_API_KEY = "k1Elhl68oqUSf2iQN3FPdtTlv3SUJW88AGsWggu4ub916a8RwHuAeoFr"
ELEVEN_API_KEY = "sk_deff42e4de20936cdf56546a4f5a25b33befbd51f26e4d94"
VOICE_ID = "TxGEqnHWrfWFTfGW9XjX" 

# Naya Gemini Client Setup
client_gemini = genai.Client(api_key=GEMINI_API_KEY)

# ================= HELPERS =================
def gpt(prompt):
    try:
        # Naya Gemini syntax (Python 3.10+ and Phone stable)
        response = client_gemini.models.generate_content(
            model="gemini-1.5-flash", 
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        print(f"Gemini Error: {e}")
        return "Error in text generation"

def get_pexels_keyword(topic):
    keyword = gpt(f"Give me only one English keyword to search stock video for: {topic}")
    return keyword if keyword else "technology"

# ================= MAIN FUNCTIONS =================

def generate_all(topic):
    script = gpt(f"Write a 30 sec viral YouTube shorts script (only spoken text): {topic}")
    title = gpt(f"Viral YouTube Shorts title (under 60 chars): {topic}")
    desc = gpt(f"SEO description with hashtags for: {topic}")
    tags_raw = gpt(f"10 comma separated tags for: {topic}")
    tags = [t.strip() for t in tags_raw.split(",")]
    return script, title, desc, tags

def download_video(topic):
    keyword = get_pexels_keyword(topic)
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={keyword}&per_page=1&orientation=portrait"
    
    res = requests.get(url, headers=headers).json()
    if "videos" in res and len(res["videos"]) > 0:
        video_url = res["videos"][0]["video_files"][0]["link"]
        with open("video.mp4", "wb") as f:
            f.write(requests.get(video_url).content)
    else:
        # Simple fallback
        raise Exception("Pexels video match nahi hua.")

def generate_voice(text):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {"xi-api-key": ELEVEN_API_KEY, "Content-Type": "application/json"}
    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    res = requests.post(url, json=data, headers=headers)
    if res.status_code == 200:
        with open("voice.mp3", "wb") as f:
            f.write(res.content)
    else:
        raise Exception("ElevenLabs voice generation failed.")

def generate_thumbnail(topic):
    # Free API for image generation
    prompt = topic.replace(" ", "%20")
    url = f"https://image.pollinations.ai/prompt/youtube_thumbnail_{prompt}?width=1024&height=1024"
    with open("thumb.png", "wb") as f:
        f.write(requests.get(url).content)

def create_video():
    # MoviePy 2.0+ (Naya structure jo crash nahi hoga)
    clip = VideoFileClip("video.mp4")
    audio = AudioFileClip("voice.mp3")

    # Audio ke hisaab se video adjust karna
    if clip.duration < audio.duration:
        clip = clip.with_effects([vfx.Loop(duration=audio.duration)])
    else:
        clip = clip.subclipped(0, audio.duration)

    final_clip = clip.with_audio(audio)
    # Write final file
    final_clip.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", logger=None)
    
    # Files close karna zaroori hai phone ki memory ke liye
    clip.close()
    audio.close()

# ================= YOUTUBE AUTH & UPLOAD =================

def youtube_auth():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
        if not os.path.exists("client_secrets.json"):
            raise Exception("client_secrets.json missing in folder!")
        flow = InstalledAppFlow.from_client_secrets_file(
            "client_secrets.json", 
            scopes=["https://www.googleapis.com/auth/youtube.upload"]
        )
        creds = flow.run_local_server(port=0)
        with open("token.pickle", "wb") as f:
            pickle.dump(creds, f)
    return build("youtube", "v3", credentials=creds)

def upload_to_yt(youtube, title, desc, tags):
    body = {
        "snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "22"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False}
    }
    media = MediaFileUpload("final.mp4", chunksize=-1, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    res = req.execute()
    
    # Thumbnail upload logic
    thumb_media = MediaFileUpload("thumb.png", mimetype="image/png")
    youtube.thumbnails().set(videoId=res["id"], media_body=thumb_media).execute()
    return res["id"]

# ================= TELEGRAM HANDLER =================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = update.message.text
    status = await update.message.reply_text(f"🚀 Starting Bot: {topic}...")
    
    try:
        await status.edit_text("✍️ Gemini is writing script...")
        script, title, desc, tags = generate_all(topic)
        
        await status.edit_text("🎵 Downloading assets...")
        download_video(topic)
        generate_voice(script)
        generate_thumbnail(topic)
        
        await status.edit_text("🎞️ Processing Video (MoviePy 2.0)...")
        create_video()
        
        await status.edit_text("📤 Uploading to YouTube...")
        yt = youtube_auth()
        video_id = upload_to_yt(yt, title, desc, tags)
        
        await status.edit_text(f"✅ Mission Success!\nURL: https://youtu.be/{video_id}")
        
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)}")

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🤖 Bot is active. Send a topic on Telegram!")
    app.run_polling()
    
