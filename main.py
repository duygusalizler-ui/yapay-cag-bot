#!/usr/bin/env python3
"""Yapay Çağ - Otomatik Viral Medya Sistemi (v3.2 - güvenli env + normalize kaynak takibi)"""
import os
import sys
import json
import time
import tempfile
import logging
from urllib.parse import urlparse, parse_qs
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("yapay-cag")

# ---------- GÜVENLİ ENV OKUMA (boş secret = varsayılan, çökme yok) ----------
def _env_str(name, default=""):
    return (os.getenv(name) or default).strip()

def _env_int(name, default):
    v = _env_str(name)
    if not v:
        return default
    try:
        return int(v)
    except ValueError:
        log.warning("⚠️ Geçersiz %s='%s' → varsayılan: %s", name, v, default)
        return default

def _env_float(name, default):
    v = _env_str(name)
    if not v:
        return default
    try:
        return float(v)
    except ValueError:
        log.warning("⚠️ Geçersiz %s='%s' → varsayılan: %s", name, v, default)
        return default

# ---------- ORTAM DEĞİŞKENLERİ ----------
SSEMBLE_BASE_URL = _env_str("SSEMBLE_BASE_URL", "https://aiclipping.ssemble.com/api/v1")
SSEMBLE_API_KEY = _env_str("SSEMBLE_API_KEY")
SSEMBLE_TEMPLATE_ID = _env_str("SSEMBLE_TEMPLATE_ID")
TELEGRAM_TOKEN = _env_str("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = _env_str("TELEGRAM_CHAT_ID")
SOURCE_URL = _env_str("SOURCE_URL")
SOURCES_FILE = _env_str("SOURCES_FILE", "sources.txt")
STATE_FILE = _env_str("STATE_FILE", "sent_state.json")
SHOPIER_CTA = _env_str("SHOPIER_CTA")
CLIP_START_SEC = _env_int("CLIP_START_SEC", 0)
CLIP_END_SEC = _env_int("CLIP_END_SEC", 600)
PREFERRED_LENGTH = _env_str("PREFERRED_LENGTH", "under60sec")
CLIP_LANGUAGE = _env_str("CLIP_LANGUAGE", "tr")
VIRAL_MIN_SCORE = _env_float("VIRAL_MIN_SCORE", 65)   # 🎯 80 değil 65
VIRAL_TOP_N = _env_int("VIRAL_TOP_N", 3)
POLL_INTERVAL = _env_int("POLL_INTERVAL", 20)
POLL_TIMEOUT = _env_int("POLL_TIMEOUT", 1800)
TG_MAX_UPLOAD = 50 * 1024 * 1024

# ---------- STATE YÖNETİMİ ----------
def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data.setdefault("sent_clips", [])
    data.setdefault("processed_sources", [])
    return data

def save_state(state):
    """Atomik yazma: önce .tmp, sonra rename → dosya bozulma riski sıfır."""
    tmp_path = STATE_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, STATE_FILE)

# ---------- KAYNAK OKUMA ----------
def read_sources():
    if SOURCE_URL:
        return [SOURCE_URL]
    try:
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f]
    except FileNotFoundError:
        return []
    return [ln for ln in lines if ln and not ln.startswith("#")]

# ---------- URL NORMALİZASYON ----------
def normalize_youtube(url):
    """youtu.be / watch?v= / ?si= hepsini tek forma çevirir (tekrar engelini sağlamlaştırır)."""
    try:
        p = urlparse(url)
        if "youtu.be" in p.netloc:
            vid = p.path.lstrip("/").split("/")[0]
            return f"https://www.youtube.com/watch?v={vid}" if vid else url
        if "youtube.com" in p.netloc:
            v = parse_qs(p.query).get("v", [None])[0]
            return f"https://www.youtube.com/watch?v={v}" if v else url
    except Exception:
        pass
    return url

def pick_target(sources, state):
    if SOURCE_URL:
        return SOURCE_URL
    processed = {normalize_youtube(s) for s in state["processed_sources"]}
    for s in sources:
        if normalize_youtube(s) not in processed:
            return s
    return None

def _unwrap(js):
    return js.get("data", js) if isinstance(js, dict) else js

# ---------- HTTP SESSION (retry'lı) ----------
def build_session(timeout=60):
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "POST"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.timeout = timeout
    return session

# ---------- SSEMBLE CLIENT ----------
class SsembleClient:
    def __init__(self, api_key, base_url=SSEMBLE_BASE_URL):
        if not api_key:
            raise RuntimeError("❌ SSEMBLE_API_KEY tanımlı değil!")
        self.base_url = base_url.rstrip("/")
        self.session = build_session(timeout=60)
        self.session.headers.update({
            "X-API-Key": api_key,
            "Content-Type": "application/json",
            "User-Agent": "YapayCagBot/3.2"
        })

    def create_short(self, source_url, template_id=None):
        payload = {
            "url": normalize_youtube(source_url),
            "start": CLIP_START_SEC,
            "end": CLIP_END_SEC,
            "preferredLength": PREFERRED_LENGTH,
            "language": CLIP_LANGUAGE
        }
        if template_id:
            payload["templateId"] = template_id

        r = self.session.post(f"{self.base_url}/shorts/create", json=payload)
        if not r.ok:
            raise RuntimeError(f"create hata {r.status_code}: {r.text[:500]}")

        data = _unwrap(r.json())
        request_id = data.get("requestId") or data.get("id")
        if not request_id:
            raise RuntimeError(f"requestId alınamadı: {data}")

        log.info("✅ Üretim başlatıldı. requestId=%s", request_id)
        return request_id

    def get_status(self, request_id):
        r = self.session.get(f"{self.base_url}/shorts/{request_id}/status")
        r.raise_for_status()
        return _unwrap(r.json()).get("status", "unknown")

    def get_shorts(self, request_id):
        r = self.session.get(f"{self.base_url}/shorts/{request_id}")
        r.raise_for_status()
        data = _unwrap(r.json())
        return data.get("shorts") or data.get("clips") or []

    def wait_until_ready(self, request_id):
        waited = 0
        while waited < POLL_TIMEOUT:
            status = self.get_status(request_id)
            log.info("⏳ Durum: %s (%ss geçti)", status, waited)
            if status == "completed":
                return True
            if status == "failed":
                raise RuntimeError("Ssemble işlemi başarısız oldu (status=failed).")
            time.sleep(POLL_INTERVAL)
            waited += POLL_INTERVAL
        raise TimeoutError(f"Zaman aşımı ({POLL_TIMEOUT}s): klipler hazır olmadı.")

# ---------- KLİP İŞLEME ----------
def clip_id(c):
    return str(c.get("id") or c.get("clipId") or c.get("url") or c.get("videoUrl") or "")

def clip_url(c):
    for k in ("url", "videoUrl", "downloadUrl", "videoUrlWithCaptions", "outputUrl"):
        if c.get(k):
            return c[k]
    return None

def clip_score(c):
    for k in ("viralScore", "score", "virality", "viralityScore"):
        if c.get(k) is not None:
            try:
                return float(c[k])
            except (TypeError, ValueError):
                pass
    return 0.0

def select_top_clips(clips, min_score, top_n):
    """İki aşamalı: 1) eşik üstü klipler 2) yoksa FALLBACK (en yüksek skorlular)."""
    for c in clips:
        c["_score"] = clip_score(c)

    log.info("📊 %d klip skorları:", len(clips))
    for i, c in enumerate(clips, 1):
        title = (c.get("title") or "Başlıksız")[:40]
        log.info("   #%d: skor=%.1f | %s", i, c["_score"], title)

    passed = [c for c in clips if c["_score"] >= min_score]
    if passed:
        log.info("✅ %d klip %s+ eşiğini geçti.", len(passed), min_score)
        passed.sort(key=lambda x: x["_score"], reverse=True)
        return passed[:top_n]

    if clips:
        log.warning("⚠️ %s+ klip yok. En yüksek skorlu %d klip seçiliyor (fallback).", min_score, top_n)
        clips.sort(key=lambda x: x["_score"], reverse=True)
        return clips[:top_n]

    return []

def download_and_verify(url):
    session = build_session(timeout=180)
    r = session.get(url, stream=True)
    r.raise_for_status()

    ct = r.headers.get("Content-Type", "").lower()
    suffix = ".webm" if "webm" in ct else ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)

    try:
        size = 0
        for chunk in r.iter_content(chunk_size=1 << 16):
            if chunk:
                tmp.write(chunk)
                size += len(chunk)
        tmp.close()

        if size == 0:
            os.unlink(tmp.name)
            raise ValueError("İndirilen dosya boş (0 byte).")

        with open(tmp.name, "rb") as f:
            head = f.read(16)

        is_mp4 = b"ftyp" in head
        is_webm = head.startswith(b"\x1a\x45\xdf\xa3")
        if not (is_mp4 or is_webm):
            os.unlink(tmp.name)
            raise ValueError(f"Dosya bütünlüğü doğrulanamadı (ne MP4 ne WebM). CT={ct}")

        log.info("✅ Doğrulandı: %s (%.1f MB)", tmp.name, size / 1e6)
        return tmp.name, size
    except Exception:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        raise

# ---------- TELEGRAM ----------
def _tg(method):
    return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"

def tg_send_message(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram tanımlı değil, mesaj atlanıyor.")
        return
    text = text[:4090]
    try:
        r = requests.post(
            _tg("sendMessage"),
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=30
        )
        r.raise_for_status()
    except Exception as e:
        log.error("Telegram mesaj hatası: %s", e)

def tg_send_video(path, caption):
    caption = (caption or "")[:1024]
    with open(path, "rb") as f:
        r = requests.post(
            _tg("sendVideo"),
            data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"},
            files={"video": f},
            timeout=300
        )
    r.raise_for_status()

def build_caption(title, desc, score):
    cta = f"\n\n{SHOPIER_CTA}" if SHOPIER_CTA.strip() else ""
    return f"🔥 <b>{title}</b>\nViral skor: {score:.0f}\n\n{desc}{cta}"

# ---------- ANA FONKSİYON ----------
def main():
    for name, val in [
        ("SSEMBLE_API_KEY", SSEMBLE_API_KEY),
        ("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
        ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)
    ]:
        if not val:
            log.error("❌ Eksik ortam değişkeni: %s", name)
            sys.exit(1)

    log.info("🚀 Yapay Çağ başlıyor... (eşik=%s, topN=%s, clip=%s-%ss)",
             VIRAL_MIN_SCORE, VIRAL_TOP_N, CLIP_START_SEC, CLIP_END_SEC)

    state = load_state()
    sources = read_sources()
    target = pick_target(sources, state)

    if not target:
        msg = ("ℹ️ İşlenecek yeni kaynak yok (kuyruk boş)." if sources
               else "⚠️ Kaynak bulunamadı: SOURCE_URL veya sources.txt tanımla.")
        tg_send_message(msg)
        log.warning(msg)
        return

    log.info("🎯 Hedef kaynak: %s", target)

    client = SsembleClient(SSEMBLE_API_KEY)
    request_id = client.create_short(target, SSEMBLE_TEMPLATE_ID or None)
    client.wait_until_ready(request_id)

    clips = client.get_shorts(request_id)
    log.info("📼 %d klip bulundu.", len(clips))

    if not clips:
        tg_send_message(f"⚠️ Ssemble hiç klip üretmedi. Kaynak: {target}\nrequestId: {request_id}")
        return

    top = select_top_clips(clips, VIRAL_MIN_SCORE, VIRAL_TOP_N)
    if not top:
        tg_send_message(f"⚠️ Hiç klip seçilemedi ({len(clips)} klip vardı).\nKaynak: {target}")
        return

    sent = 0
    sent_set = set(state["sent_clips"])

    for i, c in enumerate(top, 1):
        cid = clip_id(c)
        title = c.get("title", "Başlıksız")

        if cid and cid in sent_set:
            log.info("⏭️ #%d Zaten gönderilmiş, atlanıyor: %s", i, title)
            continue

        url = clip_url(c)
        if not url:
            log.warning("⏭️ #%d URL yok, atlanıyor: %s", i, title)
            continue

        desc = c.get("description", "")

        try:
            path, size = download_and_verify(url)
        except Exception as e:
            log.error("❌ #%d İndirme hatası (%s): %s", i, title, e)
            continue

        caption = build_caption(title, desc, c["_score"])
        path_obj = Path(path)

        try:
            if size > TG_MAX_UPLOAD:
                tg_send_message(f"{caption}\n\n▶️ Doğrudan link: {url}")
                log.info("📨 #%d Link gönderildi (>50MB).", i)
            else:
                tg_send_video(path, caption)
                log.info("📹 #%d Video gönderildi.", i)

            sent += 1
            if cid:
                sent_set.add(cid)
            state["sent_clips"] = sorted(sent_set)
            save_state(state)
        except Exception as e:
            log.error("❌ #%d Telegram hatası (%s): %s", i, title, e)
            tg_send_message(f"⚠️ Klip #{i} gönderilemedi: {title}\nHata: {e}\nURL: {url}")
        finally:
            if path_obj.exists():
                try:
                    path_obj.unlink()
                except Exception:
                    pass

    if not SOURCE_URL:
        norm = normalize_youtube(target)
        if norm not in {normalize_youtube(s) for s in state["processed_sources"]}:
            state["processed_sources"].append(norm)
    save_state(state)

    summary = (
        f"✅ <b>Otomasyon tamam</b>\n"
        f"📊 Kaynak: {target}\n"
        f"📼 Toplam klip: {len(clips)}\n"
        f"📤 Gönderilen: {sent}\n"
        f"🎯 Eşik: {VIRAL_MIN_SCORE:.0f}+\n"
        f"🆔 requestId: {request_id}"
    )
    tg_send_message(summary)
    log.info("🏁 Bitti. Gönderilen: %d / %d", sent, len(top))

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.exception("💥 Kritik hata: %s", e)
        try:
            tg_send_message(f"❌ <b>Otomasyon çöktü!</b>\n\n<pre>{str(e)[:2000]}</pre>")
        except Exception:
            pass
        sys.exit(1)
