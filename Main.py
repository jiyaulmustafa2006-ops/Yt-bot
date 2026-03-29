import os
import requests
import pickle
from moviepy.editor import VideoFileClip, AudioFileClip, vfx
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow

# ================= CONFIG (Update these) =================
TELEGRAM_TOKEN = "8080221095:AAFnsPW-6FvmUUZk2IGutf_tQFlo-CI5wdE"
OPENAI_API_KEY = "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"
PEXELS_API_KEY = "k1Elhl68oqUSf2iQN3FPdtTlv3SUJW88AGsWggu4ub916a8RwHuAeoFr"
ELEVEN_API_KEY = "sk_deff42e4de20936cdf56546a4f5a25b33befbd51f26e4d94"
VOICE_ID = "TxGEqnHWrfWFTfGW9XjX" 

client = OpenAI(api_key=OPENAI_API_KEY)

# ================= HELPERS =================
def gpt(prompt):
    res = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return res.choices[0].message.content.strip()

def get_pexels_keyword(topic):
    # Topic se 1 best keyword nikalna video search ke liye
    return gpt(f"Give me only one English keyword to search stock video for: {topic}")

# ================= MAIN FUNCTIONS =================

def generate_all(topic):
    script = gpt(f"Write a 30 sec viral YouTube shorts script (only spoken text): {topic}")
    title = gpt(f"Viral YouTube Shorts title (under 60 chars): {topic}")
    desc = gpt(f"SEO description with hashtags for: {topic}")
    tags = gpt(f"10 comma separated tags for: {topic}").split(",")
    return script, title, desc, tags

def download_video(topic):
    keyword = get_pexels_keyword(topic)
    headers = {"Authorization": PEXELS_API_KEY}
    url = f"https://api.pexels.com/videos/search?query={keyword}&per_page=5&orientation=portrait"
    
    res = requests.get(url, headers=headers).json()
    if not res.get("videos"):
        # Fallback if portrait not found
        url = f"https://api.pexels.com/videos/search?query={keyword}&per_page=1"
        res = requests.get(url, headers=headers).json()

    video_url = res["videos"][0]["video_files"][0]["link"]
    with open("video.mp4", "wb") as f:
        f.write(requests.get(video_url).content)

def generate_voice(text):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {"xi-api-key": ELEVEN_API_KEY, "Content-Type": "application/json"}
    data = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    res = requests.post(url, json=data, headers=headers)
    with open("voice.mp3", "wb") as f:
        f.write(res.content)

def generate_thumbnail(topic):
    res = client.images.generate(
        model="dall-e-3",
        prompt=f"YouTube thumbnail, cinematic, bold text: {topic}",
        size="1024x1024"
    )
    with open("thumb.png", "wb") as f:
        f.write(requests.get(res.data[0].url).content)

def create_video():
    clip = VideoFileClip("video.mp4")
    audio = AudioFileClip("voice.mp3")

    # Sync Duration
    if clip.duration < audio.duration:
        clip = clip.fx(vfx.loop, duration=audio.duration)
    else:
        clip = clip.subclip(0, audio.duration)

    # Vertical Format (9:16)
    w, h = clip.size
    target_ratio = 1080/1920
    if w/h > target_ratio:
        # Landcape ko crop karna
        new_w = h * target_ratio
        clip = clip.fx(vfx.crop, x_center=w/2, width=new_w)
    
    final_clip = clip.set_audio(audio).set_duration(audio.duration)
    # Resize to standard HD Shorts size
    final_clip = final_clip.resize(height=1920) 
    
    final_clip.write_videofile("final.mp4", fps=24, codec="libx264", audio_codec="aac", logger=None)

# ================= YOUTUBE AUTH & UPLOAD =================

def youtube_auth():
    creds = None
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as f:
            creds = pickle.load(f)
    if not creds or not creds.valid:
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
    
    # Thumbnail upload
    thumb_media = MediaFileUpload("thumb.png", mimetype="image/png")
    youtube.thumbnails().set(videoId=res["id"], media_body=thumb_media).execute()
    return res["id"]

# ================= TELEGRAM HANDLER =================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = update.message.text
    status = await update.message.reply_text(f"🎬 Processing: {topic}...")
    
    try:
        script, title, desc, tags = generate_all(topic)
        
        await status.edit_text("⏳ Downloading assets...")
        download_video(topic)
        generate_voice(script)
        generate_thumbnail(topic)
        
        await status.edit_text("✂️ Editing video (it takes a minute)...")
        create_video()
        
        await status.edit_text("🚀 Uploading to YouTube...")
        yt = youtube_auth()
        video_id = upload_to_yt(yt, title, desc, tags)
        
        await status.edit_text(f"✅ Success!\nTitle: {title}\nURL: https://youtu.be/{video_id}")
        
    except Exception as e:
        await status.edit_text(f"❌ Error: {str(e)}")

# ================= RUN =================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("🤖 Bot is live and waiting for topics...")
    app.run_polling()
