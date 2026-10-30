#!/usr/bin/env python3
"""Free-first daily AI news Short generator and YouTube uploader.

Requires GitHub Actions secrets:
GEMINI_API_KEY, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN.
No paid TTS: narration uses the runner's offline espeak-ng voice.
"""
from __future__ import annotations
import json, os, re, subprocess, sys, textwrap, time, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)
FEEDS = [
    "https://openai.com/news/rss.xml",
    "https://blog.google/technology/ai/rss/",
    "https://www.anthropic.com/news/rss.xml",
    "https://blogs.nvidia.com/feed/",
]
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing GitHub Actions secret: {name}")
    return value

def clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()

def fetch_items():
    items = []
    for feed in FEEDS:
        feed_items = []
        try:
            r = requests.get(feed, timeout=20, headers={"User-Agent":"DailyAINewsShort/1.0"})
            r.raise_for_status()
            root = ET.fromstring(r.content)
            for item in root.findall(".//item")[:8]:
                title = clean(item.findtext("title"))
                link = clean(item.findtext("link"))
                desc = clean(item.findtext("description"))
                pub = clean(item.findtext("pubDate"))
                if title and link.startswith("https://"):
                    feed_items.append({"title":title,"url":link,"summary":desc[:500],"published":pub,"domain":urlparse(link).netloc})
            if not feed_items:
                ns = {"a":"http://www.w3.org/2005/Atom"}
                for entry in root.findall(".//a:entry", ns)[:8]:
                    title = clean(entry.findtext("a:title", default="", namespaces=ns))
                    linkel = entry.find("a:link[@rel='alternate']", ns) or entry.find("a:link", ns)
                    link = linkel.attrib.get("href","") if linkel is not None else ""
                    summary = clean(entry.findtext("a:summary", default="", namespaces=ns) or entry.findtext("a:content", default="", namespaces=ns))
                    pub = clean(entry.findtext("a:published", default="", namespaces=ns) or entry.findtext("a:updated", default="", namespaces=ns))
                    if title and link.startswith("https://"):
                        feed_items.append({"title":title,"url":link,"summary":summary[:500],"published":pub,"domain":urlparse(link).netloc})
            items.extend(feed_items)
            print(f"Feed OK {feed}: {len(feed_items)} items")
        except Exception as e:
            print(f"Feed unavailable {feed}: {e}")
    unique = {x["url"]:x for x in items}
    return list(unique.values())[:24]

def generate_script(items):
    key = require_env("GEMINI_API_KEY")
    if not items:
        raise RuntimeError("No official AI news RSS items were available. Refusing to invent a story.")
    prompt = """You are an accurate technology news editor. Select one significant, recent AI development from the supplied official-source feed entries.
Write in Indian Professional English only. No Telugu or Hindi.
Do not invent facts, dates, benchmarks, prices, release status or quotes. Treat RSS summaries as leads, not proof: choose a story only when its official source URL and headline clearly support the core claim. If evidence is ambiguous, return status=skip.
Create a YouTube Short narration of 105-135 words (about 45-60 seconds), a concise title, and a description that includes the source URLs. Explain availability precisely (research preview, rollout, limited access or generally available). Avoid clickbait.
Return strict JSON with keys: status (ready or skip), title, script, description, used_urls (array).
Only use URLs from the supplied list."""
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}",
        json={"contents":[{"parts":[{"text":prompt+"\n\nOFFICIAL FEED ITEMS:\n"+json.dumps(items,ensure_ascii=False)}]}],
              "generationConfig":{"temperature":0.2,"responseMimeType":"application/json"}},
        timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"Gemini API error {resp.status_code}: {resp.text[:1000]}")
    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    data = json.loads(raw)
    if data.get("status") != "ready":
        raise RuntimeError("Gemini could not verify a suitable story today; skipped publication.")
    used = set(data.get("used_urls", []))
    sources = [x for x in items if x["url"] in used]
    if not sources:
        raise RuntimeError("Model did not cite any supplied official source. Skipping.")
    words = len(data.get("script","").split())
    if words < 75 or words > 165:
        raise RuntimeError(f"Script length outside safety range ({words} words).")
    data["sources"] = sources
    return data

def wrap_lines(text, font, draw, max_width):
    words = text.split()
    lines, line = [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if draw.textbbox((0,0), candidate, font=font)[2] <= max_width:
            line = candidate
        else:
            if line: lines.append(line)
            line = word
    if line: lines.append(line)
    return lines

def render(data):
    title = data["title"][:90]
    script = data["script"]
    (OUT/"script.txt").write_text(script, encoding="utf-8")
    (OUT/"metadata.json").write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
    voices=subprocess.run(["espeak-ng","--voices"],capture_output=True,text=True,check=True).stdout
    voice="en-in" if re.search(r"\ben-in\b",voices) else "en"
    subprocess.run(["espeak-ng","-v",voice,"-s","148","-w",str(OUT/"voice.wav"),script],check=True)
    # Build a clean 9:16 title-card background; audio + timed subtitles make a real Short.
    W,H = 720,1280
    img = Image.new("RGB",(W,H),(11,22,42))
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y/H
        c = (int(11+10*t), int(22+25*t), int(42+48*t))
        d.line((0,y,W,y),fill=c)
    regular="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    fsmall=ImageFont.truetype(regular,26)
    ftitle=ImageFont.truetype(bold,52)
    fbrand=ImageFont.truetype(bold,24)
    d.rounded_rectangle((44,54,300,104),radius=18,fill=(34,76,128))
    d.text((62,66),"DAILY AI NEWS",font=fbrand,fill=(255,255,255))
    d.text((48,190),"TODAY'S UPDATE",font=fsmall,fill=(140,190,245))
    y=270
    for line in wrap_lines(title,ftitle,d,620):
        d.text((48,y),line,font=ftitle,fill=(255,255,255),stroke_width=1)
        y += 70
    d.rounded_rectangle((48,760,672,1010),radius=24,outline=(91,145,205),width=3)
    d.text((78,800),"WHAT YOU NEED TO KNOW",font=fbrand,fill=(143,195,250))
    d.text((78,865),"AI • TECHNOLOGY • EXPLAINED",font=fsmall,fill=(230,238,248))
    d.text((48,1160),"Follow for clear, source-linked AI updates",font=fsmall,fill=(205,220,240))
    img.save(OUT/"background.png")
    # Timed captions from sentence chunks.
    chunks = re.split(r'(?<=[.!?])\s+',script.strip())
    chunks = [c.strip() for c in chunks if c.strip()]
    probe=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(OUT/"voice.wav")],capture_output=True,text=True,check=True)
    duration=float(probe.stdout.strip())
    weights=[max(1,len(c.split())) for c in chunks]
    total=sum(weights); cursor=0.0
    def stamp(sec):
        ms=int(round(sec*1000)); h=ms//3600000; ms%=3600000; m=ms//60000; ms%=60000; s=ms//1000; ms%=1000
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    with (OUT/"captions.srt").open("w",encoding="utf-8") as f:
        for i,(chunk,w) in enumerate(zip(chunks,weights),1):
            start=cursor; cursor += duration*w/total
            f.write(f"{i}\n{stamp(start)} --> {stamp(cursor)}\n{chunk}\n\n")
    # Slight motion using zoompan; burn readable captions.
    vf="scale=720:1280,zoompan=z='min(zoom+0.00025,1.08)':d=1:s=720x1280:fps=30,subtitles=output/captions.srt:force_style='FontName=DejaVu Sans,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=170'"
    subprocess.run(["ffmpeg","-y","-loop","1","-i",str(OUT/"background.png"),"-i",str(OUT/"voice.wav"),
                    "-vf",vf,"-t",str(duration),"-r","30","-c:v","libx264","-preset","veryfast","-pix_fmt","yuv420p",
                    "-c:a","aac","-b:a","128k","-shortest",str(OUT/"daily-short.mp4")],check=True)
    p=subprocess.run(["ffprobe","-v","error","-show_entries","stream=codec_type,width,height","-of","json",str(OUT/"daily-short.mp4")],capture_output=True,text=True,check=True)
    streams=json.loads(p.stdout)["streams"]
    if not any(s.get("codec_type")=="video" and s.get("width")==720 and s.get("height")==1280 for s in streams):
        raise RuntimeError("Rendered file failed vertical-video validation.")
    if not any(s.get("codec_type")=="audio" for s in streams):
        raise RuntimeError("Rendered file has no audio.")

def upload(data):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    client_id=require_env("YOUTUBE_CLIENT_ID")
    client_secret=require_env("YOUTUBE_CLIENT_SECRET")
    refresh=require_env("YOUTUBE_REFRESH_TOKEN")
    creds=Credentials(None,refresh_token=refresh,token_uri="https://oauth2.googleapis.com/token",
                      client_id=client_id,client_secret=client_secret,
                      scopes=["https://www.googleapis.com/auth/youtube.upload"])
    youtube=build("youtube","v3",credentials=creds)
    desc=data["description"].strip()+"\n\nSources:\n"+"\n".join(x["url"] for x in data["sources"])+"\n\n#AI #Technology #Shorts"
    body={"snippet":{"title":data["title"][:100],"description":desc[:4900],
                    "tags":["AI","Artificial Intelligence","Technology","AI News","Shorts"],
                    "categoryId":"28","defaultLanguage":"en"},
          "status":{"privacyStatus":os.getenv("YOUTUBE_PRIVACY","public"),
                    "selfDeclaredMadeForKids":False,"containsSyntheticMedia":True}}
    req=youtube.videos().insert(part="snippet,status",body=body,
        media_body=MediaFileUpload(str(OUT/"daily-short.mp4"),mimetype="video/mp4",chunksize=8*1024*1024,resumable=True))
    response=None
    while response is None:
        status,response=req.next_chunk()
        if status: print(f"YouTube upload: {int(status.progress()*100)}%")
    video_id=response.get("id")
    if not video_id: raise RuntimeError("YouTube API returned no video ID.")
    (OUT/"youtube-upload.json").write_text(json.dumps({"video_id":video_id,"url":f"https://youtube.com/shorts/{video_id}","uploaded_at":datetime.now(timezone.utc).isoformat()},indent=2))
    print(f"UPLOAD_SUCCESS https://youtube.com/shorts/{video_id}")

def main():
    test_mode = "--test" in sys.argv or os.getenv("TEST_MODE","").lower() in ("1","true","yes")
    if test_mode:
        items=fetch_items()
        if not items:
            raise RuntimeError("Test mode could not retrieve any official RSS entries.")
        chosen=items[0]
        data={
            "status":"ready",
            "title":"Daily AI News — Automated Pipeline Test",
            "script":("This is an automated pipeline test for the Daily AI News channel. "
                      "The system successfully retrieved an item from an official AI publisher feed. "
                      "This demo validates the narration, vertical video rendering, subtitles and artifact output. "
                      "It is not a news report and makes no claim about the linked story."),
            "description":"Automated pipeline demo. Not a news publication.",
            "used_urls":[chosen["url"]],
            "sources":[chosen]
        }
        render(data)
        print("TEST_RENDER_SUCCESS: output/daily-short.mp4")
        return
    for name in ["GEMINI_API_KEY","YOUTUBE_CLIENT_ID","YOUTUBE_CLIENT_SECRET","YOUTUBE_REFRESH_TOKEN"]:
        require_env(name)
    items=fetch_items()
    data=generate_script(items)
    render(data)
    upload(data)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print(f"WORKFLOW_FAILED: {exc}",file=sys.stderr)
        sys.exit(1)
