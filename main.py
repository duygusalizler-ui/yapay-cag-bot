#!/usr/bin/env python3
"""
Yapay Çağ - Otomatik Viral Medya Sistemi (v2)
------------------------------------------------------------
Akış:
  1) Kaynak seçer (SOURCE_URL varsa onu; yoksa sources.txt kuyruğundan
     işlenmemiş İLK videoyu).
  2) Ssemble ile klip üretimini başlatır, bitene kadar durumu yoklar.
  3) get_shorts ile klipleri + viral skorları alır.
  4) Eşiği (80+) geçen en iyi N klibi seçer.
  5) Daha önce gönderilmemiş olanları indirir, MP4/WebM bütünlüğünü doğrular,
     caption'a Shopier CTA ekleyip Telegram kanalına gönderir.
  6) State'i (gönderilen klipler + işlenen kaynaklar) kaydeder, özet rapor atar.

NOT: Ssemble API'si resmî olarak MCP sunucusu olarak da sunulur (anahtar
formatı sk_ssemble_...). Aşağıdaki REST yolları belgelenmiş araç şemasına
(create_short / get_status / get_shorts) göredir; kesin adresi panelden
doğrula, farklıysa SSEMBLE_BASE_URL'i güncelle. Mantık aynı kalır.
"""

import os
import sys
import json
import time
import tempfile
import logging
import requests

# --- Yapılandırma -----------------------------------------------------------
SSEMBLE_BASE_URL = os.getenv("SSEMBLE_BASE_URL", "https://api.ssemble.com/v1")
SSEMBLE_API_KEY = os.environ.get("SSEMBLE_API_KEY", "")
SSEMBLE_TEMPLATE_ID = os.getenv("SSEMBLE_TEMPLATE_ID", "")

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

SOURCE_URL = os.getenv("SOURCE_URL", "")            # tekil override / manuel test
SOURCES_FILE = os.getenv("SOURCES_FILE", "sources.txt")
STATE_FILE = os.getenv("STATE_FILE", "sent_state.json")
SHOPIER_CTA = os.getenv("SHOPIER_CTA", "")          # ör: "🛒 https://shopier.com/..."

VIRAL_MIN_SCORE = float(os.getenv("VIRAL_MIN_SCORE", "80"))
VIRAL_TOP_N = int(os.getenv("VIRAL_TOP_N", "3"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "20"))
POLL_TIMEOUT = int(os.getenv("POLL_TIMEOUT", "1800"))

TG_MAX_UPLOAD = 50 * 1024 * 1024  # Telegram bot yükleme limiti (~50 MB)

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("yapay-cag")


# --- State (kalıcılık) ------------------------------------------------------
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
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def read_sources():
    """SOURCE_URL varsa onu döndür; yoksa sources.txt satırlarını oku."""
    if SOURCE_URL.strip():
        return [SOURCE_URL.strip()]
    try:
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f]
    except FileNotFoundError:
        return []
    return [ln for ln in lines if ln and not ln.startswith("#")]


def pick_target(sources, state):
    """SOURCE_URL override ise onu işle; değilse kuyruktan işlenmemiş ilkini seç."""
    if SOURCE_URL.strip():
        return SOURCE_URL.strip()
    for s in sources:
        if s not in state["processed_sources"]:
            return s
    return None


# --- Ssemble istemcisi ------------------------------------------------------
class SsembleClient:
    def __init__(self, api_key, base_url=SSEMBLE_BASE_URL):
        if not api_key:
            raise RuntimeError("SSEMBLE_API_KEY tanımlı değil.")
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "SSEMBLE_API_KEY": api_key,
            "Content-Type": "application/json",
        })

    def create_short(self, source_url, template_id=None):
        payload = {"youtubeUrl": source_url}
        if template_id:
            payload["templateId"] = template_id
        r = self.session.post(f"{self.base_url}/shorts", json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        request_id = data.get("requestId") or data.get("id")
        if not request_id:
            raise RuntimeError(f"requestId alınamadı: {data}")
        log.info("Üretim başlatıldı. requestId=%s", request_id)
        return request_id

    def get_status(self, request_id):
        r = self.session.get(f"{self.base_url}/shorts/{request_id}/status", timeout=30)
        r.raise_for_status()
        return r.json().get("status", "unknown")

    def get_shorts(self, request_id):
        r = self.session.get(f"{self.base_url}/shorts/{request_id}", timeout=30)
        r.raise_for_status()
        data = r.json()
        return data.get("shorts") or data.get("clips") or []

    def wait_until_ready(self, request_id):
        waited = 0
        while waited < POLL_TIMEOUT:
            status = self.get_status(request_id)
            log.info("Durum: %s (%ss)", status, waited)
            if status == "completed":
                return True
            if status == "failed":
                raise RuntimeError("Ssemble işlemi başarısız oldu.")
            time.sleep(POLL_INTERVAL)
            waited += POLL_INTERVAL
        raise TimeoutError("Zaman aşımı: klipler zamanında hazır olmadı.")


# --- Yardımcılar ------------------------------------------------------------
def clip_id(c):
    return str(c.get("id") or c.get("clipId") or c.get("url") or c.get("videoUrl") or "")


def select_top_clips(clips, min_score, top_n):
    scored = []
    for c in clips:
        raw = c.get("viralScore", c.get("score", 0)) or 0
        try:
            score = float(raw)
        except (TypeError, ValueError):
            score = 0.0
        c["_score"] = score
        if score >= min_score:
            scored.append(c)
    scored.sort(key=lambda x: x["_score"], reverse=True)
    return scored[:top_n]


def download_and_verify(url):
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    suffix = ".webm" if "webm" in r.headers.get("Content-Type", "").lower() else ".mp4"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    size = 0
    for chunk in r.iter_content(chunk_size=1 << 16):
        if chunk:
            tmp.write(chunk)
            size += len(chunk)
    tmp.close()
    if size == 0:
        os.unlink(tmp.name)
        raise ValueError("İndirilen dosya boş.")
    with open(tmp.name, "rb") as f:
        head = f.read(16)
    if not (b"ftyp" in head or head.startswith(b"\x1a\x45\xdf\xa3")):
        os.unlink(tmp.name)
        raise ValueError("Dosya bütünlüğü doğrulanamadı (MP4/WebM değil).")
    log.info("Doğrulandı: %s (%.1f MB)", tmp.name, size / 1e6)
    return tmp.name, size


# --- Telegram ---------------------------------------------------------------
def _tg(method):
    return f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"


def tg_send_message(text):
    r = requests.post(_tg("sendMessage"),
                      data={"chat_id": TELEGRAM_CHAT_ID, "text": text,
                            "parse_mode": "HTML"}, timeout=30)
    r.raise_for_status()


def tg_send_video(path, caption):
    caption = (caption or "")[:1024]
    with open(path, "rb") as f:
        r = requests.post(_tg("sendVideo"),
                          data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption,
                                "parse_mode": "HTML"},
                          files={"video": f}, timeout=300)
    r.raise_for_status()


def build_caption(title, desc, score):
    cta = f"\n\n{SHOPIER_CTA}" if SHOPIER_CTA.strip() else ""
    return f"🔥 <b>{title}</b>\nViral skor: {score:.0f}\n\n{desc}{cta}"


# --- Ana akış ---------------------------------------------------------------
def main():
    for name, val in [("SSEMBLE_API_KEY", SSEMBLE_API_KEY),
                      ("TELEGRAM_TOKEN", TELEGRAM_TOKEN),
                      ("TELEGRAM_CHAT_ID", TELEGRAM_CHAT_ID)]:
        if not val:
            log.error("Eksik ortam değişkeni: %s", name)
            sys.exit(1)

    state = load_state()
    sources = read_sources()
    target = pick_target(sources, state)

    if not target:
        msg = "ℹ️ İşlenecek yeni kaynak yok (kuyruk boş)." if sources \
              else "⚠️ Kaynak bulunamadı: SOURCE_URL veya sources.txt tanımla."
        tg_send_message(msg)
        log.warning(msg)
        return

    log.info("Hedef kaynak: %s", target)
    client = SsembleClient(SSEMBLE_API_KEY)
    request_id = client.create_short(target, SSEMBLE_TEMPLATE_ID or None)
    client.wait_until_ready(request_id)

    clips = client.get_shorts(request_id)
    log.info("%d klip bulundu.", len(clips))
    top = select_top_clips(clips, VIRAL_MIN_SCORE, VIRAL_TOP_N)

    sent = 0
    sent_set = set(state["sent_clips"])
    for c in top:
        cid = clip_id(c)
        if cid and cid in sent_set:
            log.info("Zaten gönderilmiş, atlanıyor: %s", cid)
            continue
        url = c.get("url") or c.get("videoUrl")
        if not url:
            continue
        title = c.get("title", "Başlıksız")
        desc = c.get("description", "")
        try:
            path, size = download_and_verify(url)
        except Exception as e:
            log.error("Klip atlandı (%s): %s", title, e)
            continue
        caption = build_caption(title, desc, c["_score"])
        try:
            if size > TG_MAX_UPLOAD:
                tg_send_message(f"{caption}\n\n▶️ {url}")
            else:
                tg_send_video(path, caption)
            sent += 1
            if cid:
                sent_set.add(cid)
            state["sent_clips"] = sorted(sent_set)
            save_state(state)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    if not SOURCE_URL.strip() and target not in state["processed_sources"]:
        state["processed_sources"].append(target)
    save_state(state)

    tg_send_message(f"✅ Otomasyon tamam. Kaynak işlendi, {sent} klip gönderildi.\n"
                    f"(requestId: {request_id})")
    log.info("Bitti. Gönderilen: %d", sent)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.exception("Kritik hata: %s", e)
        try:
            tg_send_message(f"❌ Otomasyon hatası: {e}")
        except Exception:
            pass
        sys.exit(1)
