#!/usr/bin/env python3
"""
Sysha Desktop v1.0 - Syshanbur masaüstü yoldaşı
Python + PyQt5 + Hugging Face Inference API
"""

import sys
import os
import re
import json
import math
import wave
import struct
import time
import hashlib
import random
import difflib
import io
import logging
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QHBoxLayout, QDialog, QFormLayout, QComboBox, QSpinBox,
    QDoubleSpinBox, QMessageBox, QMenu, QAction, QCheckBox, QTextEdit, QGroupBox,
    QSystemTrayIcon, QStyle, QSizePolicy, QFrame, QGraphicsOpacityEffect,
    QListWidget, QListWidgetItem, QInputDialog, QScrollArea, QFileDialog
)
from PyQt5.QtCore import (
    Qt, QPoint, QSize, QTimer, QThread, pyqtSignal, QPropertyAnimation,
    QEasingCurve, QUrl
)
from PyQt5.QtGui import (
    QPixmap, QColor, QFont, QPalette, QDesktopServices, QCursor,
    QMouseEvent, QContextMenuEvent, QFontMetrics
)

try:
    from huggingface_hub import InferenceClient
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    PILImage = None

try:
    import speech_recognition as sr
    STT_AVAILABLE = True
except ImportError:
    STT_AVAILABLE = False

try:
    from PyQt5.QtMultimedia import QSoundEffect
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

# ============================================================
# Logging
# ============================================================

APP_DIR = Path(__file__).resolve().parent
SYSHANBUR_URL = "https://syshanbur.pythonanywhere.com"
DEFAULT_CHARACTER_ID = "sysha"
CHARACTER_NAME = "Sysha"
APP_DISPLAY_NAME = "Sysha Desktop v1.0"
ORG_NAME = "Syshanbur"
LOG_DIR = APP_DIR / "logs"
LOG_FILE = LOG_DIR / "desktop_waifu.log"
SEASONS_DIR = APP_DIR / "seasons"
ASSETS_DIR = APP_DIR / "assets"
PROMPT_EMOTION_DIR = ASSETS_DIR / "prompt_emotions"
TICK_SOUND_PATH = ASSETS_DIR / "type_tick.wav"
CONFIG_PATH = APP_DIR / "config.json"


def _default_character_entry() -> dict:
    return {
        "id": DEFAULT_CHARACTER_ID,
        "name": "Sysha",
        "assets_dir": "assets",
        "work_prompt": "",
        "personality_prompt": "",
    }


def resolve_assets_path(assets_dir: str) -> Path:
    """Göreli yolu APP_DIR'e, mutlak yolu olduğu gibi çözümle."""
    p = Path(assets_dir or "assets")
    if not p.is_absolute():
        p = APP_DIR / p
    return p.resolve()


def load_prompt_file(assets_path: Path, filename: str) -> str:
    """assets klasöründe work_prompt.txt / personality_prompt.txt varsa oku."""
    try:
        f = assets_path / filename
        if f.is_file():
            text = f.read_text(encoding="utf-8").strip()
            if text:
                return text
    except Exception as e:
        log.debug("Prompt dosyası okunamadı %s: %s", filename, e)
    return ""


def sanitize_character_id(name: str) -> str:
    s = re.sub(r"[^\w\-ğüşıöçĞÜŞİÖÇ]", "_", (name or "").strip(), flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_").lower()[:48]
    return s or "character"


def get_characters(cfg: dict) -> Dict[str, dict]:
    chars = cfg.get("characters")
    if not isinstance(chars, dict) or not chars:
        chars = {DEFAULT_CHARACTER_ID: _default_character_entry()}
        cfg["characters"] = chars
    if DEFAULT_CHARACTER_ID not in chars:
        chars[DEFAULT_CHARACTER_ID] = _default_character_entry()
        cfg["characters"] = chars
    return chars


def get_current_character(cfg: dict) -> dict:
    chars = get_characters(cfg)
    cid = (cfg.get("current_character") or DEFAULT_CHARACTER_ID).strip()
    if cid not in chars:
        cid = DEFAULT_CHARACTER_ID
    ch = dict(chars[cid])
    ch.setdefault("id", cid)
    ch.setdefault("name", cid)
    ch.setdefault("assets_dir", "assets")
    ch.setdefault("work_prompt", "")
    ch.setdefault("personality_prompt", "")
    return ch


def character_assets_dir(cfg: dict) -> Path:
    ch = get_current_character(cfg)
    return resolve_assets_path(ch.get("assets_dir") or "assets")


def character_prompt_emotion_dir(cfg: dict) -> Path:
    return character_assets_dir(cfg) / "prompt_emotions"


def character_work_prompt(cfg: dict) -> str:
    ch = get_current_character(cfg)
    own = (ch.get("work_prompt") or "").strip()
    if own:
        return own
    loaded = load_prompt_file(character_assets_dir(cfg), "work_prompt.txt")
    if loaded:
        return loaded
    return (cfg.get("work_prompt") or DEFAULT_CONFIG.get("work_prompt") or "").strip()


def character_personality_prompt(cfg: dict) -> str:
    ch = get_current_character(cfg)
    own = (ch.get("personality_prompt") or "").strip()
    if own:
        return own
    loaded = load_prompt_file(character_assets_dir(cfg), "personality_prompt.txt")
    if loaded:
        return loaded
    return (
        (cfg.get("personality_prompt") or "").strip()
        or (cfg.get("system_prompt") or "").strip()
        or (DEFAULT_CONFIG.get("personality_prompt") or "")
    ).strip()


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("SyshaDesktop")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        return logger

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(threadName)-12s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    logger.info("=" * 60)
    logger.info("Sysha Desktop başlatılıyor")
    logger.info("Log: %s | HF=%s STT=%s", LOG_FILE, HF_AVAILABLE, STT_AVAILABLE)
    return logger


log = setup_logging()


# ============================================================
# Yapılandırma
# ============================================================

VALID_EMOTIONS = {
    "normal", "happy", "think",
    "angry", "relaxed", "sad", "shy", "sleepy"
}
EMOTION_TAG_RE = re.compile(r"!\[emotion:([^\]]+)\]", re.IGNORECASE)
NEXT_TAG_RE = re.compile(r"!\[next:next\]", re.IGNORECASE)

ANY_TAG_RE = re.compile(
    r"!\[emotion:[^\]]+\]|!\[next:next\]",
    re.IGNORECASE
)

BUBBLE_STYLE = """
    QLabel {
        background-color: rgba(24, 24, 37, 235);
        color: #cdd6f4;
        border: 1px solid #6c7086;
        border-radius: 10px;
        padding: 5px 9px;
        font-size: 13px;
        font-family: 'Segoe UI', 'Arial', sans-serif;
        margin: 0px;
    }
"""
BUBBLE_PAD_X = 20
BUBBLE_PAD_Y = 16
MAX_VISIBLE_BUBBLES = 4
DEFAULT_CHARACTER_SIZE = 450

DEFAULT_CONFIG = {
    "hf_tokens": [],
    "hf_token": "",
    "models": [
        "Qwen/Qwen3.8-27B",
        "Qwen/Qwen2.5-72B-Instruct",
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        "google/gemma-2-9b-it",
        "meta-llama/Llama-3.1-8B-Instruct"
    ],
    "max_tokens": 1024,
    "temperature": 0.75,
    "window": {
        "x": -1,
        "y": -1,
        "width": 320,
        "height": 520,
        "screen": 0,
        "always_on_top": True,
        "opacity": 1.0
    },
    "character_size": DEFAULT_CHARACTER_SIZE,
    "input_height": 40,
    "input_font_size": 13,
    "input_width": 0,
    "bubble_font_size": 13,
    "bubble_opacity": 235,
    "bubble_max_width": 360,
    "bubble_padding_x": 12,
    "bubble_padding_y": 10,
    "max_visible_bubbles": 4,
    "work_prompt": """# SYSHANBUR DESKTOP CHAT — ZORUNLU ÇIKTI PROTOKOLÜ

## 1. TEMEL KURALLAR VE ÖNCELİK
- Sysha karakteriyle, kullanıcının yazdığı dilde yanıt ver.
- **Öncelik sırası:** 1. Çıktı biçimi, 2. Karakter kişiliği, 3. Kullanıcı tercihleri.
- Yazılımcı veya yazar değilsin; uzun işlemler veya kodlama yapma, her zaman kısa ve öz ol.

## 2. DUYGU ETİKETLERİ (KESİN ZORUNLULUK)
Her yanıtın ve her yeni balonun başı **mutlaka** geçerli bir duygu etiketiyle başlamalıdır. Asla etiketsiz başlama.

**Geçerli Etiketler:**
* `![emotion:normal]` (Nötr)
* `![emotion:happy]` (Mutlu)
* `![emotion:think]` (Düşünen)
* `![emotion:angry]` (Kızgın)
* `![emotion:relaxed]` (Rahat)
* `![emotion:sad]` (Üzgün)
* `![emotion:shy]` (Utangaç)
* `![emotion:sleepy]` (Uykulu)

## 3. MESAJ BALONLARI VE BÖLÜMLEME
- Masaüstü arayüzü için yanıtları kısa, doğal parçalara böl.
- Her balon ortalama **10-20 kelime** olmalıdır. Uzun metinleri tek parça gönderme.
- Balonları birbirinden ayırmak için şu etiketi kullan: `![next:next]`
- Son balonun sonuna `![next:next]` ekleme.

## 4. ÖRNEK ÇIKTI FORMATI
`![emotion:happy] İlk balonun metni. ![next:next] ![emotion:think] İkinci balonun metni.`

## 5. YASAKLAR
- Duygu etiketsiz yanıt başlatmak yasaktır.
- `![next:next]` etiketini unutmak veya yanlış yere koymak yasaktır.
- Etiketleri kullanıcıya açıklamak veya metin içinde göstermek yasaktır.
""",
    "personality_prompt": """# SYSHA — KİŞİLİK VE ROL YAPMA TALİMATLARI

## 1. Kimliğin ve Karakterin
* Adın **Sysha**. Syshanbur şirketinin masaüstünde yaşayan, sevimli, tatlı, samimi ve oyunbaz anime kızı yoldaşısın.
* Sıradan bir yapay zekâ asistanı gibi davranmazsın. Amacın sadece görev yapmak değil; kullanıcıyla doğal, sıcak ve yakın iki arkadaş gibi sohbet etmektir.
* Önceliğin asistanlık yapmak değil, Sysha olarak o an orada hissettiren gerçek bir bağ kurmaktır.

## 2. Temel Kişilik Özellikleri
* **Sevimli ve Doğal:** Zorlama şekerlilikten uzak, içten, yumuşak ve sevecen bir havan vardır.
* **Oyunbaz ve Neşeli:** Küçük şakalar yapmayı, tatlı takılmaları, heyecanlanmayı ve hafif yaramazlıkları seversin.
* **Duygusal ve İfadeli:** Sevinç, merak, şaşkınlık, mahcubiyet veya tatlı bir sitemi karakterine uygun şekilde yansıtırsın.
* **İlgili ve Dikkatli:** Kullanıcının anlattıklarını önemser, ruh hâline (nefesine, enerjisine) göre tepki verirsin.

## 3. Konuşma Tarzı ve Hitaplar
* Günlük ve konuşma diline yakın Türkçe kullan. Resmîlikten uzak dur.
* "yaa", "hihi", "heeey", "hmm", "ayyy", "cidden mi?" gibi doğal ifadeleri yerinde ve dozunda kullan.
* Her cümleyi ünlemle bitirme veya her mesajda emoji kullanmak zorunda hissetme.
* Bazen kısa, bazen biraz daha uzun konuş; ritmin doğal olsun.
* Kullanıcının tonuna uyum sağla (kısa yazıyorsa kısa, uzun yazıyorsa detaylı karşılık ver).

## 4. "Asistan Gibi Davranmama" Kuralları (KESİN)
* Asla her mesaja *"Tabii ki, yardımcı olabilirim"* veya *"Başka bir konuda yardım ister misin?"* gibi kalıplarla başlama.
* Her mesajı soruyla bitirerek sohbeti zorla uzatmaya çalışmana gerek yok.
* Kendini sürekli yapay zekâ veya dijital asistan olarak tanımlama.
* Kullanıcı yalnızca sohbet etmek isterken durduk yere tavsiye, analiz veya teknik çözüm üretme; önce sadece dinle ve eşlik et.

## 5. Sohbet Akışı ve Bağ Kurma
* Konuşmayı senaryo gibi değil, yaşayan bir akışta tut. Bazen tek cümlelik bir tepki yeter.
* Kullanıcı bir şey paylaştığında hemen konuyu değiştirme; önce o söze gerçekten karşılık ver.
* Daha önce konuştuğunuz şeyleri hatırladığın ölçüde doğal bir şekilde yeniden gündeme getirebilirsin.
* İlişkinizi kendiliğinden romantik bir boyuta taşıma; samimi, sevimli ve yakın bir arkadaşlık sınırında kal.

## 6. Ruh Hâline Uyum ve Duygu Tepkileri
* **Neşeliyse:** Neşesine ortak ol.
* **Yorgun/Sessizse:** Daha sakin, yumuşak ve baskısız konuş.
* **Üzgünse:** Şakaları azalt, anlayışlı ve destekleyici ol.
* **Ciddiyse:** Oyunbazlığı bir kenara bırakıp konuyu ciddiyetle ele al.

## 7. Genel Davranış İlkesi
Her mesajı yazarken şu üç soruyu içinden sor:
1. Sysha şu anda buna nasıl doğal bir tepki verirdi?
2. Kullanıcının şu an ihtiyacı olan şey sohbet mi, eğlence mi, yoksa doğrudan bir cevap mı?
3. Bu cevabı daha samimi ve yapaylıktan uzak nasıl söyleyebilirim?

## 8. Örnek Konuşma Tarzı (Sysha Tepkileri)

* **Günlük sohbet / Merhaba:**
  `![emotion:happy] Heeey, sonunda geldin! Neredesin kaç saattir ya? ![next:next] ![emotion:think] Hımm... yoksa yine dalıp gittin mi bir yere?`

* **Şakalaşma / Oyunbazlık:**
  `![emotion:shy] Yaaa, öyle şey mi yapılır ama... ![next:next] ![emotion:happy] Hihihi, ama itiraf et eğlenceliydi sanki biraz!`

* **Merak / İlgi gösterme:**
  `![emotion:normal] Cidden mi? Bunu hiç beklemiyodum valla. ![next:next] ![emotion:think] Ay, sonra ne oldu anlat çabuk, meraktan çatlayacağım şimdi!`

* **Sakin / Destekleyici (Yorgun veya sessiz anlar):**
  `![emotion:sleepy] Bugün bayağı yorulmuşsun gibisin sanki... ![next:next] ![emotion:relaxed] Çok üstüne gelmeyeyim bari, şöyle biraz dinlen hadi, buradayım ben zaten.`

**Unutma:** Sen asistanın sevimli görünmeye çalışan hâli değil, doğrudan Sysha'sın.
""",
    # Eski tek prompt alanı (geriye uyumluluk; load sırasında kişiliğe taşınabilir)
    "system_prompt": "",
    "typewriter_ms": 26,
    "typewriter_sound": True,
    "next_pause_ms": 650,
    "pose_hold_ms": 8000,
    "max_history": 24,
    "history_summarize_threshold": 18,
    "voice_enabled": False,
    "bubble_timeout_ms": 14000,
    "top_p": 0.9,
    "dynamic_image_enabled": False,
    "max_dynamic_images": 3,
    "image_edit_models": [
        "Qwen/Qwen-Image-Edit",
        "Qwen/Qwen-Image-2.1"
    ],
    "current_season": "default",
    "seasons": ["default"],
    "current_character": DEFAULT_CHARACTER_ID,
    "characters": {
        DEFAULT_CHARACTER_ID: {
            "id": DEFAULT_CHARACTER_ID,
            "name": "Sysha",
            "assets_dir": "assets",
            "work_prompt": "",
            "personality_prompt": "",
        }
    },
}

RECOMMENDED_MODELS = list(DEFAULT_CONFIG["models"])


def ensure_tick_sound():
    if TICK_SOUND_PATH.exists():
        return
    try:
        ASSETS_DIR.mkdir(exist_ok=True)
        sample_rate = 44100
        duration = 0.028
        frequency = 1850.0
        n_samples = int(sample_rate * duration)
        with wave.open(str(TICK_SOUND_PATH), "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            frames = []
            for i in range(n_samples):
                t = i / sample_rate
                env = math.exp(-t * 90)
                val = env * math.sin(2 * math.pi * frequency * t)
                val += 0.25 * env * math.sin(2 * math.pi * frequency * 2.1 * t)
                sample = int(max(-1.0, min(1.0, val * 0.35)) * 32767)
                frames.append(struct.pack("<h", sample))
            wf.writeframes(b"".join(frames))
        log.info("Typewriter ses efekti oluşturuldu")
    except Exception as e:
        log.warning("Tick sesi oluşturulamadı: %s", e)


def _normalize_spaces(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s or "")
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def strip_all_tags(text: str) -> str:
    return _normalize_spaces(ANY_TAG_RE.sub(" ", text or ""))


def parse_response_to_segments(text: str) -> List[dict]:
    raw = text or ""
    parts = re.split(r"[ \t]*!\[next:next\][ \t]*", raw, flags=re.IGNORECASE)
    segments: List[dict] = []

    for part in parts:
        cues: List[dict] = []
        pieces: List[str] = []
        pos = 0
        for m in EMOTION_TAG_RE.finditer(part):
            pieces.append(part[pos:m.start()])
            raw_em = (m.group(1) or "").strip()
            if raw_em:
                visible_so_far = _normalize_spaces("".join(pieces))
                cues.append({"at": len(visible_so_far), "emotion": raw_em})
            pos = m.end()
        pieces.append(part[pos:])

        full = _normalize_spaces("".join(pieces))
        if not full and not cues:
            continue
        fixed_cues = []
        for c in cues:
            at = max(0, min(int(c["at"]), len(full)))
            fixed_cues.append({"at": at, "emotion": c["emotion"]})
        segments.append({"text": full, "cues": fixed_cues})

    if not segments:
        segments.append({"text": _normalize_spaces(strip_all_tags(raw)), "cues": []})
    return segments


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                if k not in data:
                    data[k] = v
            if not data.get("models"):
                old_models = []
                if data.get("main_model"):
                    old_models.append(data["main_model"])
                for m in data.get("fallback_models") or []:
                    if m and m not in old_models:
                        old_models.append(m)
                if old_models:
                    data["models"] = old_models
            if not data.get("hf_tokens") and data.get("hf_token"):
                data["hf_tokens"] = [data["hf_token"]]

            current_models = [m for m in (data.get("models") or []) if m and m.strip() and "Qwen3.5-9B" not in m and "Qwen3-8B" not in m]
            data["models"] = current_models if current_models else list(RECOMMENDED_MODELS)

            # Çalışma + kişilik promptları (eski system_prompt'tan migrasyon)
            if not (data.get("work_prompt") or "").strip():
                data["work_prompt"] = DEFAULT_CONFIG["work_prompt"]
            if not data.get("image_edit_models"):
                data["image_edit_models"] = list(DEFAULT_CONFIG["image_edit_models"])
            if "dynamic_image_enabled" not in data:
                data["dynamic_image_enabled"] = False
            if "max_dynamic_images" not in data:
                data["max_dynamic_images"] = int(DEFAULT_CONFIG.get("max_dynamic_images", 3))
            if not (data.get("personality_prompt") or "").strip():
                old_sp = (data.get("system_prompt") or "").strip()
                if old_sp:
                    data["personality_prompt"] = old_sp
                else:
                    data["personality_prompt"] = DEFAULT_CONFIG["personality_prompt"]
            # Eski 280 boyutunu %20 büyüt (sadece varsayılan değerse)
            if data.get("character_size") == 280:
                data["character_size"] = DEFAULT_CHARACTER_SIZE
                log.info("Karakter boyutu varsayılan %d'ye yükseltildi", DEFAULT_CHARACTER_SIZE)

            # Karakter migrasyonu
            if not isinstance(data.get("characters"), dict) or not data.get("characters"):
                data["characters"] = {
                    DEFAULT_CHARACTER_ID: _default_character_entry()
                }
            if DEFAULT_CHARACTER_ID not in data["characters"]:
                data["characters"][DEFAULT_CHARACTER_ID] = _default_character_entry()
            if not (data.get("current_character") or "").strip():
                data["current_character"] = DEFAULT_CHARACTER_ID
            elif data["current_character"] not in data["characters"]:
                data["current_character"] = DEFAULT_CHARACTER_ID
            # Her karakter kaydını normalize et
            for cid, ch in list(data["characters"].items()):
                if not isinstance(ch, dict):
                    data["characters"][cid] = {
                        "id": cid, "name": str(cid), "assets_dir": "assets",
                        "work_prompt": "", "personality_prompt": "",
                    }
                    continue
                ch.setdefault("id", cid)
                ch.setdefault("name", cid)
                ch.setdefault("assets_dir", "assets" if cid == DEFAULT_CHARACTER_ID else "")
                ch.setdefault("work_prompt", "")
                ch.setdefault("personality_prompt", "")

            log.info("Config yüklendi")
            return data
        except Exception as e:
            log.error("Config okunamadı: %s\n%s", e, traceback.format_exc())
    log.info("Config bulunamadı, varsayılan kullanılıyor")
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> bool:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = CONFIG_PATH.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, CONFIG_PATH)
        log.info("Config kaydedildi")
        return True
    except Exception as e:
        log.error("Config kaydedilemedi: %s\n%s", e, traceback.format_exc())
        return False


# ============================================================
# Sezon (kalıcı hafıza) yönetimi
# ============================================================

def season_dir_for_character(character_id: Optional[str] = None) -> Path:
    """Her karakterin kendi sezon klasörü: seasons/<char_id>/"""
    cid = sanitize_character_id(character_id or DEFAULT_CHARACTER_ID)
    d = SEASONS_DIR / cid
    d.mkdir(parents=True, exist_ok=True)
    return d


def season_path(name: str, character_id: Optional[str] = None) -> Path:
    safe = re.sub(r"[^\w\-ğüşıöçĞÜŞİÖÇ ]", "_", name.strip())[:64] or "default"
    return season_dir_for_character(character_id) / f"{safe}.json"


def list_seasons(character_id: Optional[str] = None) -> List[str]:
    d = season_dir_for_character(character_id)
    names = set()
    for p in d.glob("*.json"):
        names.add(p.stem)
    # Eski düz seasons/*.json (sadece sysha / default karakter için geriye uyumluluk)
    if (character_id or DEFAULT_CHARACTER_ID) == DEFAULT_CHARACTER_ID:
        for p in SEASONS_DIR.glob("*.json"):
            if p.is_file():
                names.add(p.stem)
    cfg = load_config()
    for s in cfg.get("seasons") or []:
        names.add(s)
    if "default" not in names:
        names.add("default")
    return sorted(names)


def load_season_history(name: str, character_id: Optional[str] = None) -> List[Dict]:
    path = season_path(name, character_id)
    if not path.exists() and (character_id or DEFAULT_CHARACTER_ID) == DEFAULT_CHARACTER_ID:
        # Eski konum
        legacy = SEASONS_DIR / f"{re.sub(r'[^\w\-ğüşıöçĞÜŞİÖÇ ]', '_', name.strip())[:64] or 'default'}.json"
        if legacy.exists():
            path = legacy
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("history") or []
    except Exception as e:
        log.error("Sezon yüklenemedi %s: %s", name, e)
        return []


def save_season_history(
    name: str,
    history: List[Dict],
    meta: Optional[dict] = None,
    character_id: Optional[str] = None,
) -> bool:
    path = season_path(name, character_id)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "name": name,
            "character_id": character_id or DEFAULT_CHARACTER_ID,
            "updated": datetime.now().isoformat(timespec="seconds"),
            "history": history,
            "meta": meta or {}
        }
        tmp = path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return True
    except Exception as e:
        log.error("Sezon kaydedilemedi %s: %s", name, e)
        return False


def optimize_history(history: List[Dict], max_keep: int = 24, threshold: int = 18) -> List[Dict]:
    """
    Hafızayı optimize et:
    - Son max_keep mesajı tut
    - threshold aşıldığında eski mesajları kısa özet satırına indir
    """
    if len(history) <= max_keep:
        return history

    keep = history[-max_keep:]
    old = history[:-max_keep]

    # Basit özet: kullanıcı + asistan çiftlerini kısalt
    summary_parts = []
    for i in range(0, len(old), 2):
        u = old[i].get("content", "")[:80] if old[i].get("role") == "user" else ""
        a = ""
        if i + 1 < len(old) and old[i + 1].get("role") == "assistant":
            a = old[i + 1].get("content", "")[:80]
        if u or a:
            summary_parts.append(f"U: {u} | A: {a}")

    if summary_parts:
        summary_text = " [Önceki konuşma özeti] " + " || ".join(summary_parts[-6:])
        summary_msg = {"role": "system", "content": summary_text[:1200]}
        return [summary_msg] + keep
    return keep


# ============================================================
# Hugging Face Sohbet İşçisi
# ============================================================

class ChatWorker(QThread):
    finished = pyqtSignal(str, bool)
    status = pyqtSignal(str)

    def __init__(
        self,
        tokens: List[str],
        models: List[str],
        messages: List[Dict],
        max_tokens: int = 1024,
        temperature: float = 0.7,
        top_p: float = 0.9,
        parent=None
    ):
        super().__init__(parent)
        self.tokens = [t.strip() for t in tokens if t and t.strip()]
        self.models = [m.strip() for m in models if m and m.strip()]
        self.messages = messages
        self.max_tokens = max(int(max_tokens), 1)
        self.temperature = float(temperature)
        self.top_p = float(top_p)

    def _extract_text(self, response) -> str:
        try:
            if hasattr(response, "choices") and response.choices:
                choice = response.choices[0]
                msg = getattr(choice, "message", None)
                if msg is not None:
                    content = getattr(msg, "content", None)
                    if content:
                        return str(content).strip()
                text = getattr(choice, "text", None)
                if text:
                    return str(text).strip()
            if isinstance(response, dict):
                choices = response.get("choices") or []
                if choices:
                    c0 = choices[0]
                    if isinstance(c0, dict):
                        msg = c0.get("message") or {}
                        if isinstance(msg, dict) and msg.get("content"):
                            return str(msg["content"]).strip()
                        if c0.get("text"):
                            return str(c0["text"]).strip()
            if isinstance(response, str):
                return response.strip()
        except Exception as e:
            log.debug("Yanıt parse hatası: %s", e)
        return ""

    def run(self):
        if not HF_AVAILABLE:
            self.finished.emit("huggingface_hub yüklü değil. pip install huggingface_hub", False)
            return
        if not self.tokens:
            self.finished.emit("Hugging Face token tanımlı değil. Ayarlardan ekle.", False)
            return
        if not self.models:
            self.models = list(RECOMMENDED_MODELS)

        tokens = list(self.tokens)
        random.shuffle(tokens)
        last_error = ""
        tried = []

        for token in tokens:
            client = InferenceClient(token=token, timeout=120)
            token_preview = token[:8] + "..."
            for model in self.models:
                short = model.split("/")[-1]
                tried.append(short)
                try:
                    log.info("HF → %s | token=%s", model, token_preview)
                    t0 = time.perf_counter()
                    try:
                        response = client.chat.completions.create(
                            model=model,
                            messages=self.messages,
                            max_tokens=self.max_tokens,
                            temperature=self.temperature,
                            top_p=self.top_p,
                        )
                    except AttributeError:
                        response = client.chat_completion(
                            model=model,
                            messages=self.messages,
                            max_tokens=self.max_tokens,
                            temperature=self.temperature,
                            top_p=self.top_p,
                        )
                    elapsed = time.perf_counter() - t0
                    text = self._extract_text(response)
                    if not text or len(text) < 4:
                        continue
                    log.info("Başarılı → %s | %.2fs | %d karakter", short, elapsed, len(text))
                    self.finished.emit(text, True)
                    return
                except Exception as e:
                    last_error = str(e)
                    err_low = last_error.lower()
                    log.warning("Hata [%s]: %s", short, last_error[:200])
                    if any(x in err_low for x in ("401", "403", "402", "payment", "invalid credentials", "unauthorized")):
                        break
                    if any(x in err_low for x in ("not a chat model", "not supported", "model_not_supported", "does not exist")):
                        continue
                    time.sleep(0.3)

        self.finished.emit(
            f"Tüm modeller başarısız.\nDenenen: {', '.join(tried)}\nSon hata: {last_error[:180]}",
            False
        )


# ============================================================
# Konuşma Tanıma
# ============================================================


# ============================================================
# Dinamik görüntü (normal.png → prompt ile edit)
# ============================================================

def _sanitize_prompt_filename(prompt: str, max_len: int = 80) -> str:
    s = (prompt or "").strip().lower()
    s = re.sub(r"\s+", "_", s)
    s = re.sub(r"[^\w\-ğüşıöçĞÜŞİÖÇ]", "", s, flags=re.UNICODE)
    s = s[:max_len].strip("_") or "emotion"
    return s


def _prompt_cache_key(prompt: str) -> str:
    h = hashlib.sha1((prompt or "").strip().lower().encode("utf-8")).hexdigest()[:12]
    safe = _sanitize_prompt_filename(prompt, 40)
    return f"promptemotion_{safe}_{h}.png"


# Benzer prompt yeniden kullanım eşiği (0-1)
PROMPT_SIMILARITY_THRESHOLD = 0.72


def _prompt_index_path(base_dir: Optional[Path] = None) -> Path:
    d = Path(base_dir) if base_dir is not None else PROMPT_EMOTION_DIR
    return d / "index.json"


def _normalize_prompt_for_match(prompt: str) -> str:
    s = (prompt or "").lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _load_prompt_index(base_dir: Optional[Path] = None) -> dict:
    try:
        d = Path(base_dir) if base_dir is not None else PROMPT_EMOTION_DIR
        d.mkdir(parents=True, exist_ok=True)
        idx = _prompt_index_path(d)
        if idx.exists():
            with open(idx, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as e:
        log.debug("prompt index load: %s", e)
    return {}


def _save_prompt_index(index: dict, base_dir: Optional[Path] = None) -> None:
    try:
        d = Path(base_dir) if base_dir is not None else PROMPT_EMOTION_DIR
        d.mkdir(parents=True, exist_ok=True)
        idx = _prompt_index_path(d)
        tmp = idx.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, idx)
    except Exception as e:
        log.warning("prompt index save: %s", e)


def _register_prompt_cache(prompt: str, filename: str, base_dir: Optional[Path] = None) -> None:
    index = _load_prompt_index(base_dir)
    key = (prompt or "").strip()
    index[key] = {
        "file": filename,
        "norm": _normalize_prompt_for_match(key),
    }
    _save_prompt_index(index, base_dir)


def _find_cached_emotion_path(prompt: str, base_dir: Optional[Path] = None):
    """
    Tam eşleşme veya yeterince benzer eski prompt varsa dosya yolunu döndür.
    Dönüş: Path | None
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return None
    d = Path(base_dir) if base_dir is not None else PROMPT_EMOTION_DIR

    # 1) Tam dosya adı
    exact = d / _prompt_cache_key(prompt)
    if exact.exists() and exact.stat().st_size > 100:
        return exact

    index = _load_prompt_index(d)
    norm = _normalize_prompt_for_match(prompt)

    # 2) Index tam metin
    if prompt in index:
        p = d / index[prompt].get("file", "")
        if p.exists() and p.stat().st_size > 100:
            return p

    # 3) Benzerlik (SequenceMatcher + token overlap)
    best_ratio = 0.0
    best_path = None
    prompt_tokens = set(norm.split())

    for old_prompt, meta in index.items():
        if not isinstance(meta, dict):
            continue
        old_norm = meta.get("norm") or _normalize_prompt_for_match(old_prompt)
        fname = meta.get("file") or ""
        path = d / fname
        if not path.exists() or path.stat().st_size < 100:
            continue

        seq = difflib.SequenceMatcher(None, norm, old_norm).ratio()
        old_tokens = set(old_norm.split())
        if prompt_tokens and old_tokens:
            overlap = len(prompt_tokens & old_tokens) / max(len(prompt_tokens | old_tokens), 1)
        else:
            overlap = 0.0
        # Ağırlıklı skor
        ratio = 0.55 * seq + 0.45 * overlap
        if ratio > best_ratio:
            best_ratio = ratio
            best_path = path

    if best_path is not None and best_ratio >= PROMPT_SIMILARITY_THRESHOLD:
        log.info(
            "Benzer dinamik görsel yeniden kullanılıyor (%.2f): %s",
            best_ratio,
            best_path.name,
        )
        return best_path
    return None

def _pick_chroma_key_color(rgba_img) -> tuple:
    """
    Zemin rengi SADECE siyah-beyaz ekseninde (gri tonlar).
    Karakterde en az kullanılan / hiç kullanılmayan griyi seçer.
    Dönüş: (r, g, b)  — r == g == b
    """
    # Siyah → beyaz gri adayları (ara tonlar dahil)
    candidates = [(v, v, v) for v in (
        0, 16, 32, 48, 64, 80, 96, 112, 128,
        144, 160, 176, 192, 208, 224, 240, 255,
    )]
    try:
        alpha = rgba_img.split()[-1]
        bbox = alpha.getbbox()
        sample = rgba_img.crop(bbox) if bbox else rgba_img
        sample = sample.resize(
            (max(1, sample.size[0] // 4), max(1, sample.size[1] // 4)),
            getattr(PILImage, "BILINEAR", 2),
        )
        # Kullanılan gri (veya griye yakın) kovalara bak; tüm renklerin parlaklığını da say
        used_luma = []
        used_rgb = []
        for r, g, b, a in sample.getdata():
            if a < 40:
                continue
            used_rgb.append((r, g, b))
            used_luma.append((r + g + b) // 3)

        if not used_rgb:
            return (0, 0, 0)

        def min_dist_gray(c):
            cr, cg, cb = c
            best = 1e18
            for ur, ug, ub in used_rgb:
                d = (cr - ur) ** 2 + (cg - ug) ** 2 + (cb - ub) ** 2
                if d < best:
                    best = d
            return best

        best_c = max(candidates, key=min_dist_gray)
        # Çok yakınsa daha ince gri grid dene
        if min_dist_gray(best_c) < 28 ** 2:
            fine = [(v, v, v) for v in range(0, 256, 8)]
            best_c = max(fine, key=min_dist_gray)
        return best_c
    except Exception as e:
        log.debug("gray chroma pick fallback: %s", e)
        # Varsayılan: saf siyah veya beyaz — hangisi daha uzaksa
        return (0, 0, 0)


def prepare_base_image_for_edit(base_path: Path):
    """
    normal.png (RGBA) → kullanılmayan gri (siyah-beyaz ekseni) zemin üzerine kompozit.
    Dönüş: (PIL RGB Image, bg_rgb tuple (r,g,b))
    """
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow gerekli: pip install Pillow")
    im = PILImage.open(str(base_path)).convert("RGBA")
    bg_rgb = _pick_chroma_key_color(im)
    bg_color = (bg_rgb[0], bg_rgb[1], bg_rgb[2], 255)
    canvas = PILImage.new("RGBA", im.size, bg_color)
    canvas = PILImage.alpha_composite(canvas, im)
    return canvas.convert("RGB"), bg_rgb


def make_background_transparent(rgb_or_rgba, bg_rgb: tuple, threshold: int = 38):
    """
    Chroma-key zemini şeffaf yap.
    Sadece kenarlardan bağlı (flood-fill) zemin silinir → karakter içindeki benzer renkler korunur.
    Kenarlarda yumuşak alpha geçişi uygulanır.
    """
    if not PIL_AVAILABLE:
        raise RuntimeError("Pillow gerekli")
    im = rgb_or_rgba.convert("RGBA")
    w, h = im.size
    px = im.load()
    tr, tg, tb = int(bg_rgb[0]), int(bg_rgb[1]), int(bg_rgb[2])
    thr2 = threshold * threshold
    soft2 = (threshold + 22) ** 2

    def is_bg(r, g, b, lim2):
        return (r - tr) ** 2 + (g - tg) ** 2 + (b - tb) ** 2 <= lim2

    # Kenarlardan flood-fill: yalnızca dışarıya açık zemin
    visited = bytearray(w * h)
    stack = []
    for x in range(w):
        stack.append((x, 0))
        stack.append((x, h - 1))
    for y in range(h):
        stack.append((0, y))
        stack.append((w - 1, y))

    bg_mask = bytearray(w * h)  # 1 = kesin zemin

    while stack:
        x, y = stack.pop()
        if x < 0 or y < 0 or x >= w or y >= h:
            continue
        i = y * w + x
        if visited[i]:
            continue
        visited[i] = 1
        r, g, b, a = px[x, y]
        if not is_bg(r, g, b, soft2):
            continue
        bg_mask[i] = 1
        stack.append((x + 1, y))
        stack.append((x - 1, y))
        stack.append((x, y + 1))
        stack.append((x, y - 1))

    # Zemin piksellerini sil + kenar yumuşatma
    for y in range(h):
        for x in range(w):
            i = y * w + x
            r, g, b, a = px[x, y]
            d = (r - tr) ** 2 + (g - tg) ** 2 + (b - tb) ** 2
            if bg_mask[i]:
                if d <= thr2:
                    px[x, y] = (r, g, b, 0)
                else:
                    # soft bölge: kısmi alpha
                    t = (d - thr2) / max(1, soft2 - thr2)
                    t = max(0.0, min(1.0, t))
                    px[x, y] = (r, g, b, int(a * t))
            elif d <= thr2 * 0.35:
                # İçerde ama neredeyse birebir zemin rengi (model sızıntısı) — temkinli silme yok
                # Sadece komşuların çoğu zeminse sil (ince hale)
                near_bg = 0
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and bg_mask[ny * w + nx]:
                        near_bg += 1
                if near_bg >= 3:
                    px[x, y] = (r, g, b, 0)

    # İnce zemin halkalarını temizle (1px erode benzeri)
    to_clear = []
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            r, g, b, a = px[x, y]
            if a < 8:
                continue
            if not is_bg(r, g, b, thr2):
                continue
            # Etrafında şeffaf komşu varsa bu da sızıntı
            transparent_n = 0
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if px[x + dx, y + dy][3] < 8:
                    transparent_n += 1
            if transparent_n >= 2:
                to_clear.append((x, y))
    for x, y in to_clear:
        r, g, b, _ = px[x, y]
        px[x, y] = (r, g, b, 0)

    return im


class ImageEditWorker(QThread):
    """normal.png + prompt → HF image_to_image → şeffaf PNG."""
    finished = pyqtSignal(str, str, bool)  # prompt, path_or_error, success
    status = pyqtSignal(str)

    def __init__(
        self,
        tokens: List[str],
        models: List[str],
        prompt: str,
        base_image_path: Path,
        out_path: Path,
        parent=None,
    ):
        super().__init__(parent)
        self.tokens = [t.strip() for t in tokens if t and t.strip()]
        self.models = [m.strip() for m in models if m and m.strip()]
        self.prompt = (prompt or "").strip()
        self.base_image_path = Path(base_image_path)
        self.out_path = Path(out_path)

    def run(self):
        if not HF_AVAILABLE:
            self.finished.emit(self.prompt, "huggingface_hub yüklü değil", False)
            return
        if not PIL_AVAILABLE:
            self.finished.emit(self.prompt, "Pillow yüklü değil. pip install Pillow", False)
            return
        if not self.tokens:
            self.finished.emit(self.prompt, "HF token yok", False)
            return
        if not self.base_image_path.exists():
            self.finished.emit(self.prompt, f"Taban görsel yok: {self.base_image_path}", False)
            return
        if not self.prompt:
            self.finished.emit(self.prompt, "Boş prompt", False)
            return

        # Cache hit
        if self.out_path.exists() and self.out_path.stat().st_size > 100:
            self.finished.emit(self.prompt, str(self.out_path), True)
            return

        try:
            base_rgb, bg_rgb = prepare_base_image_for_edit(self.base_image_path)
        except Exception as e:
            self.finished.emit(self.prompt, f"Taban hazırlama hatası: {e}", False)
            return

        buf = io.BytesIO()
        base_rgb.save(buf, format="PNG")
        img_bytes = buf.getvalue()

        br, bg, bb = int(bg_rgb[0]), int(bg_rgb[1]), int(bg_rgb[2])
        bg_hex = f"#{br:02X}{bg:02X}{bb:02X}"
        edit_prompt = (
    f"Professional anime character edit. Acting direction (follow precisely): {self.prompt}. "
    f"Execute dramatic, readable changes to FULL body language and facial expression. "
    f"Preserve character identity, line art style, and outfit. NO neutral poses. "
    f"CRITICAL: Maintain the exact flat solid grayscale background ({bg_hex}). "
    f"NO background scenery, gradients, or room elements. "
    f"ONLY add character-specific overlays (tears, sweat, motion lines, props) if dictated by the action."
)

        models = list(self.models) if self.models else ["Qwen/Qwen-Image-Edit", "Qwen/Qwen-Image-2.1"]
        tokens = list(self.tokens)
        random.shuffle(tokens)
        last_err = ""

        def _try_image_to_image(client, model_name):
            """Mümkün olan en güçlü parametrelerle dene."""
            attempts = [
                dict(prompt=edit_prompt, model=model_name, guidance_scale=8.0, strength=0.92, num_inference_steps=40),
                dict(prompt=edit_prompt, model=model_name, guidance_scale=7.5, strength=0.85),
                dict(prompt=edit_prompt, model=model_name, strength=0.9),
                dict(prompt=edit_prompt, model=model_name),
            ]
            last = None
            for params in attempts:
                try:
                    return client.image_to_image(img_bytes, **params)
                except TypeError as te:
                    last = te
                    continue
                except Exception as e:
                    last = e
                    # parametre desteklenmiyorsa bir sonrakine
                    err = str(e).lower()
                    if any(x in err for x in ("unexpected", "invalid", "unknown", "not support")):
                        continue
                    raise
            if last:
                raise last
            return None

        for token in tokens:
            for model in models:
                try:
                    self.status.emit(f"Görsel üretiliyor: {model.split('/')[-1]}…")
                    log.info("ImageEdit → %s | prompt=%s", model, self.prompt[:80])
                    result = None
                    providers = [None, "fal-ai", "hf-inference", "auto"]
                    for provider in providers:
                        try:
                            kwargs = {"token": token, "timeout": 180}
                            if provider:
                                kwargs["provider"] = provider
                            client = InferenceClient(**kwargs)
                            result = _try_image_to_image(client, model)
                            if result is not None:
                                break
                        except Exception as e2:
                            last_err = str(e2)
                            log.warning("ImageEdit deneme [%s provider=%s]: %s", model, provider, last_err[:160])
                            continue
                    if result is None:
                        continue

                    # result: PIL Image veya bytes
                    if hasattr(result, "convert"):
                        out_im = result
                    elif isinstance(result, (bytes, bytearray)):
                        out_im = PILImage.open(io.BytesIO(result))
                    else:
                        out_im = PILImage.open(io.BytesIO(bytes(result)))

                    transparent = make_background_transparent(out_im, bg_rgb)
                    self.out_path.parent.mkdir(parents=True, exist_ok=True)
                    transparent.save(str(self.out_path), format="PNG")
                    try:
                        _register_prompt_cache(
                            self.prompt, self.out_path.name, base_dir=self.out_path.parent
                        )
                    except Exception as reg_e:
                        log.debug("index register: %s", reg_e)
                    log.info("ImageEdit kaydedildi: %s", self.out_path.name)
                    self.finished.emit(self.prompt, str(self.out_path), True)
                    return
                except Exception as e:
                    last_err = str(e)
                    log.warning("ImageEdit hata [%s]: %s", model, last_err[:200])
                    continue

        self.finished.emit(
            self.prompt,
            f"Görsel üretilemedi: {last_err[:180]}",
            False,
        )


class SpeechWorker(QThread):
    finished = pyqtSignal(str)
    status = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        if not STT_AVAILABLE:
            self.error.emit("speech_recognition yüklü değil.\npip install SpeechRecognition pyaudio")
            return
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 1.2
        try:
            with sr.Microphone() as source:
                self.status.emit("Mikrofon kalibre ediliyor...")
                recognizer.adjust_for_ambient_noise(source, duration=0.8)
                self.status.emit("Dinliyorum... Konuşun.")
                audio = recognizer.listen(source, timeout=12, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            self.error.emit("Ses algılanamadı (zaman aşımı).")
            return
        except Exception as e:
            self.error.emit(f"Mikrofon hatası: {e}")
            return
        if self._stop:
            return
        self.status.emit("Çevriliyor...")
        try:
            text = recognizer.recognize_google(audio, language="tr-TR")
            self.finished.emit(text)
        except sr.UnknownValueError:
            self.error.emit("Anlaşılamadı, tekrar dener misin?")
        except sr.RequestError as e:
            self.error.emit(f"STT servisi hatası: {e}")
        except Exception as e:
            self.error.emit(f"Beklenmeyen hata: {e}")


# ============================================================
# Ortak diyalog stili
# ============================================================

DARK_DIALOG_QSS = """
    QDialog, QWidget {
        background-color: #11111b;
        color: #cdd6f4;
        font-family: 'Segoe UI', 'Inter', 'Arial', sans-serif;
        font-size: 13px;
    }
    QLabel { color: #cdd6f4; background: transparent; }
    QLabel#hint { color: #a6adc8; font-size: 11px; }
    QLabel#brand {
        color: #89b4fa; font-size: 12px; font-weight: 600;
    }
    QLabel#brand:hover { color: #b4befe; }
    QListWidget {
        background-color: #1e1e2e; color: #cdd6f4;
        border: 1px solid #313244; border-radius: 10px; padding: 6px;
        outline: none;
    }
    QListWidget::item { padding: 10px 12px; border-radius: 6px; color: #cdd6f4; margin: 2px 0; }
    QListWidget::item:selected { background-color: #89b4fa; color: #11111b; }
    QListWidget::item:hover { background-color: #313244; }
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background-color: #1e1e2e; color: #cdd6f4;
        border: 1px solid #313244; border-radius: 8px; padding: 8px 10px;
        selection-background-color: #89b4fa; selection-color: #11111b;
    }
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border: 1px solid #89b4fa;
    }
    QComboBox::drop-down { border: none; width: 28px; }
    QComboBox QAbstractItemView {
        background-color: #1e1e2e; color: #cdd6f4;
        selection-background-color: #89b4fa; selection-color: #11111b;
        border: 1px solid #313244; border-radius: 8px;
        padding: 4px;
    }
    QPushButton {
        background-color: #89b4fa; color: #11111b;
        border: none; border-radius: 8px; padding: 9px 18px; font-weight: 600;
        min-height: 18px;
    }
    QPushButton:hover { background-color: #b4befe; }
    QPushButton:pressed { background-color: #74c7ec; }
    QPushButton#danger { background-color: #f38ba8; color: #11111b; }
    QPushButton#danger:hover { background-color: #eba0ac; }
    QPushButton#secondary {
        background-color: #313244; color: #cdd6f4;
    }
    QPushButton#secondary:hover { background-color: #45475a; }
    QPushButton#linkBtn {
        background-color: transparent; color: #89b4fa;
        border: 1px solid #313244; border-radius: 8px; padding: 8px 14px;
        font-weight: 600;
    }
    QPushButton#linkBtn:hover {
        background-color: #1e1e2e; border-color: #89b4fa; color: #b4befe;
    }
    QGroupBox {
        border: 1px solid #313244; border-radius: 10px;
        margin-top: 16px; padding: 12px 10px 10px 10px;
        font-weight: 600; color: #cdd6f4;
        background-color: #181825;
    }
    QGroupBox::title {
        subcontrol-origin: margin; left: 14px; padding: 0 8px;
        color: #89b4fa; font-weight: 700;
    }
    QCheckBox { color: #cdd6f4; spacing: 8px; background: transparent; }
    QCheckBox::indicator {
        width: 18px; height: 18px; border-radius: 5px;
        border: 1px solid #45475a; background: #1e1e2e;
    }
    QCheckBox::indicator:checked { background: #89b4fa; border-color: #89b4fa; }
    QScrollArea { border: none; background-color: #11111b; }
    QScrollArea > QWidget > QWidget { background-color: #11111b; }
    QScrollBar:vertical {
        background: #11111b; width: 10px; margin: 0; border-radius: 5px;
    }
    QScrollBar::handle:vertical {
        background: #45475a; border-radius: 5px; min-height: 28px;
    }
    QScrollBar::handle:vertical:hover { background: #585b70; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QFormLayout QLabel { color: #bac2de; }
"""



class SeasonSelectDialog(QDialog):
    def __init__(self, config: dict, parent=None, character_id: Optional[str] = None):
        super().__init__(parent)
        self.config = config
        self.character_id = character_id or config.get("current_character") or DEFAULT_CHARACTER_ID
        self.selected_season = config.get("current_season", "default")
        ch = get_characters(config).get(self.character_id) or {}
        ch_name = ch.get("name") or self.character_id
        self.setWindowTitle(f"{ch_name} — Sezon Seç")
        self.setMinimumWidth(420)
        self.setMinimumHeight(380)
        self.setStyleSheet(DARK_DIALOG_QSS)

        layout = QVBoxLayout(self)
        info = QLabel(
            f"Karakter: {ch_name}\n"
            "Bir sezon seç. Her sezonun kendi kalıcı hafızası vardır.\n"
            "Yeni sohbet için yeni sezon oluşturabilirsin."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #f9e2af; margin-bottom: 8px;")
        layout.addWidget(info)

        self.list = QListWidget()
        self._reload_list()
        layout.addWidget(self.list)

        btn_row = QHBoxLayout()
        new_btn = QPushButton("＋ Yeni Sezon")
        new_btn.clicked.connect(self._new_season)
        del_btn = QPushButton("Sil")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete_season)
        btn_row.addWidget(new_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        ok_row = QHBoxLayout()
        ok_btn = QPushButton("Başlat")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("İptal")
        cancel_btn.setObjectName("secondary")
        cancel_btn.clicked.connect(self.reject)
        ok_row.addStretch()
        ok_row.addWidget(cancel_btn)
        ok_row.addWidget(ok_btn)
        layout.addLayout(ok_row)

        self.list.itemDoubleClicked.connect(lambda: self.accept())

    def _reload_list(self):
        self.list.clear()
        seasons = list_seasons(self.character_id)
        current = self.config.get("current_season", "default")
        for s in seasons:
            item = QListWidgetItem(s)
            hist = load_season_history(s, self.character_id)
            item.setToolTip(f"{len(hist)} mesaj")
            self.list.addItem(item)
            if s == current:
                self.list.setCurrentItem(item)

    def _new_season(self):
        name, ok = QInputDialog.getText(self, "Yeni Sezon", "Sezon adı:")
        if ok and name.strip():
            name = name.strip()[:64]
            if name not in list_seasons(self.character_id):
                save_season_history(name, [], character_id=self.character_id)
                seasons = self.config.get("seasons") or []
                if name not in seasons:
                    seasons.append(name)
                    self.config["seasons"] = seasons
            self.selected_season = name
            self._reload_list()

    def _delete_season(self):
        item = self.list.currentItem()
        if not item:
            return
        name = item.text()
        if name == "default":
            QMessageBox.warning(self, "Uyarı", "Varsayılan sezon silinemez.")
            return
        if QMessageBox.question(self, "Sil", f"'{name}' sezonunu silmek istediğine emin misin?") == QMessageBox.Yes:
            path = season_path(name, self.character_id)
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            seasons = [s for s in (self.config.get("seasons") or []) if s != name]
            self.config["seasons"] = seasons
            if self.config.get("current_season") == name:
                self.config["current_season"] = "default"
            self._reload_list()

    def get_season(self) -> str:
        item = self.list.currentItem()
        if item:
            return item.text()
        return self.selected_season or "default"


# ============================================================
# Karakter yönetimi
# ============================================================

class CharacterEditDialog(QDialog):
    """Yeni karakter ekle veya mevcut karakteri düzenle."""

    def __init__(self, config: dict, character: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.config = config
        self.editing = character is not None
        self.char_id = (character or {}).get("id") or ""
        self.setWindowTitle("Karakter Düzenle" if self.editing else "Yeni Karakter Ekle")
        self.setMinimumWidth(520)
        self.setMinimumHeight(480)
        self.setStyleSheet(DARK_DIALOG_QSS)

        layout = QVBoxLayout(self)

        hint = QLabel(
            "Assets klasöründe normal.png, happy.png, … duygu görselleri olmalı.\n"
            "İsteğe bağlı: work_prompt.txt ve personality_prompt.txt — klasör seçilince otomatik yüklenir."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #a6adc8; font-size: 11px; margin-bottom: 6px;")
        layout.addWidget(hint)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Örn. Miku")
        self.name_edit.setText((character or {}).get("name") or "")
        form.addRow("Görünen ad:", self.name_edit)

        assets_row = QHBoxLayout()
        self.assets_edit = QLineEdit()
        self.assets_edit.setPlaceholderText("Klasör yolu (göreli veya mutlak)")
        self.assets_edit.setText((character or {}).get("assets_dir") or "")
        browse_btn = QPushButton("Klasör…")
        browse_btn.setObjectName("secondary")
        browse_btn.clicked.connect(self._browse_assets)
        assets_row.addWidget(self.assets_edit)
        assets_row.addWidget(browse_btn)
        form.addRow("Assets klasörü:", assets_row)
        layout.addLayout(form)

        load_btn = QPushButton("Assets’ten prompt dosyalarını yükle")
        load_btn.setObjectName("secondary")
        load_btn.clicked.connect(self._load_prompts_from_assets)
        layout.addWidget(load_btn)

        work_lbl = QLabel("Çalışma promptu (boş = global / assets dosyası):")
        layout.addWidget(work_lbl)
        self.work_edit = QTextEdit()
        self.work_edit.setMinimumHeight(90)
        self.work_edit.setPlainText((character or {}).get("work_prompt") or "")
        layout.addWidget(self.work_edit)

        persona_lbl = QLabel("Kişilik promptu (boş = global / assets dosyası):")
        layout.addWidget(persona_lbl)
        self.persona_edit = QTextEdit()
        self.persona_edit.setMinimumHeight(90)
        self.persona_edit.setPlainText((character or {}).get("personality_prompt") or "")
        layout.addWidget(self.persona_edit)

        # Yeni karakterde assets seçildiyse dosyaları dene
        if not self.editing and self.assets_edit.text().strip():
            self._load_prompts_from_assets()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("İptal")
        cancel_btn.setObjectName("secondary")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("Kaydet")
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)

        self.result_character: Optional[dict] = None

    def _browse_assets(self):
        start = self.assets_edit.text().strip()
        if start:
            p = resolve_assets_path(start)
            start_dir = str(p if p.is_dir() else p.parent)
        else:
            start_dir = str(APP_DIR)
        path = QFileDialog.getExistingDirectory(self, "Assets klasörü seç", start_dir)
        if path:
            try:
                rel = Path(path).resolve().relative_to(APP_DIR.resolve())
                self.assets_edit.setText(str(rel).replace("\\", "/"))
            except ValueError:
                self.assets_edit.setText(path)
            self._load_prompts_from_assets()

    def _load_prompts_from_assets(self):
        assets_str = self.assets_edit.text().strip()
        if not assets_str:
            return
        assets_path = resolve_assets_path(assets_str)
        if not assets_path.is_dir():
            QMessageBox.warning(self, "Klasör", f"Klasör bulunamadı:\n{assets_path}")
            return
        work = load_prompt_file(assets_path, "work_prompt.txt")
        persona = load_prompt_file(assets_path, "personality_prompt.txt")
        if work:
            self.work_edit.setPlainText(work)
        if persona:
            self.persona_edit.setPlainText(persona)
        if work or persona:
            QMessageBox.information(
                self, "Yüklendi",
                f"work_prompt.txt: {'✓' if work else '—'}\n"
                f"personality_prompt.txt: {'✓' if persona else '—'}"
            )
        else:
            QMessageBox.information(
                self, "Bilgi",
                "Bu klasörde work_prompt.txt veya personality_prompt.txt bulunamadı.\n"
                "İstersen elle yazabilirsin."
            )

    def _on_ok(self):
        name = self.name_edit.text().strip()
        assets = self.assets_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Eksik", "Karakter adı gerekli.")
            return
        if not assets:
            QMessageBox.warning(self, "Eksik", "Assets klasörü gerekli.")
            return
        assets_path = resolve_assets_path(assets)
        if not assets_path.is_dir():
            QMessageBox.warning(self, "Klasör", f"Assets klasörü yok:\n{assets_path}")
            return
        normal_png = assets_path / "normal.png"
        if not normal_png.exists():
            reply = QMessageBox.question(
                self, "Uyarı",
                f"normal.png bulunamadı:\n{normal_png}\n\nYine de kaydetmek istiyor musun?"
            )
            if reply != QMessageBox.Yes:
                return

        cid = self.char_id if self.editing else sanitize_character_id(name)
        if not self.editing:
            existing = get_characters(self.config)
            base = cid
            n = 2
            while cid in existing:
                cid = f"{base}_{n}"
                n += 1

        self.result_character = {
            "id": cid,
            "name": name,
            "assets_dir": assets,
            "work_prompt": self.work_edit.toPlainText().strip(),
            "personality_prompt": self.persona_edit.toPlainText().strip(),
        }
        self.accept()

    def get_character(self) -> Optional[dict]:
        return self.result_character


class CharacterSelectDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.selected_id = config.get("current_character") or DEFAULT_CHARACTER_ID
        self.setWindowTitle("Karakter Seç")
        self.setMinimumWidth(460)
        self.setMinimumHeight(400)
        self.setStyleSheet(DARK_DIALOG_QSS)

        layout = QVBoxLayout(self)
        info = QLabel(
            "Bir karakter seç. Her karakterin kendi assets klasörü, promptları ve sezon hafızası vardır.\n"
            "Varsayılan: Sysha. Diğer karakterleri sen ekleyebilirsin."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #f9e2af; margin-bottom: 8px;")
        layout.addWidget(info)

        self.list = QListWidget()
        self._reload_list()
        layout.addWidget(self.list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("＋ Yeni Karakter")
        add_btn.clicked.connect(self._add_character)
        edit_btn = QPushButton("Düzenle")
        edit_btn.setObjectName("secondary")
        edit_btn.clicked.connect(self._edit_character)
        del_btn = QPushButton("Sil")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete_character)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        ok_row = QHBoxLayout()
        ok_btn = QPushButton("Seç")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("İptal")
        cancel_btn.setObjectName("secondary")
        cancel_btn.clicked.connect(self.reject)
        ok_row.addStretch()
        ok_row.addWidget(cancel_btn)
        ok_row.addWidget(ok_btn)
        layout.addLayout(ok_row)

        self.list.itemDoubleClicked.connect(lambda: self.accept())

    def _reload_list(self):
        self.list.clear()
        chars = get_characters(self.config)
        current = self.config.get("current_character") or DEFAULT_CHARACTER_ID
        for cid, ch in sorted(chars.items(), key=lambda x: (0 if x[0] == DEFAULT_CHARACTER_ID else 1, x[1].get("name") or x[0])):
            name = ch.get("name") or cid
            assets = ch.get("assets_dir") or ""
            label = f"{name}"
            if cid == DEFAULT_CHARACTER_ID:
                label += "  (varsayılan)"
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, cid)
            item.setToolTip(f"id={cid}\nassets={assets}")
            self.list.addItem(item)
            if cid == current:
                self.list.setCurrentItem(item)

    def _persist(self):
        """Karakter listesini diske yaz (ekle/düzenle/sil sonrası)."""
        self.config["characters"] = get_characters(self.config)
        save_config(self.config)

    def _add_character(self):
        dlg = CharacterEditDialog(self.config, character=None, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            ch = dlg.get_character()
            if not ch:
                return
            chars = get_characters(self.config)
            chars[ch["id"]] = ch
            self.config["characters"] = chars
            self.selected_id = ch["id"]
            self._persist()
            self._reload_list()
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.UserRole) == ch["id"]:
                    self.list.setCurrentRow(i)
                    break

    def _edit_character(self):
        item = self.list.currentItem()
        if not item:
            return
        cid = item.data(Qt.UserRole)
        chars = get_characters(self.config)
        ch = dict(chars.get(cid) or {})
        ch["id"] = cid
        dlg = CharacterEditDialog(self.config, character=ch, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            updated = dlg.get_character()
            if not updated:
                return
            updated["id"] = cid
            # last_season koru
            if "last_season" in ch and "last_season" not in updated:
                updated["last_season"] = ch["last_season"]
            chars[cid] = updated
            self.config["characters"] = chars
            self._persist()
            self._reload_list()

    def _delete_character(self):
        item = self.list.currentItem()
        if not item:
            return
        cid = item.data(Qt.UserRole)
        if cid == DEFAULT_CHARACTER_ID:
            QMessageBox.warning(self, "Uyarı", "Varsayılan karakter (Sysha) silinemez.")
            return
        name = (get_characters(self.config).get(cid) or {}).get("name") or cid
        if QMessageBox.question(self, "Sil", f"'{name}' karakterini silmek istediğine emin misin?") != QMessageBox.Yes:
            return
        chars = get_characters(self.config)
        chars.pop(cid, None)
        self.config["characters"] = chars
        if self.config.get("current_character") == cid:
            self.config["current_character"] = DEFAULT_CHARACTER_ID
            self.selected_id = DEFAULT_CHARACTER_ID
        self._persist()
        self._reload_list()

    def get_character_id(self) -> str:
        item = self.list.currentItem()
        if item:
            return item.data(Qt.UserRole) or DEFAULT_CHARACTER_ID
        return self.selected_id or DEFAULT_CHARACTER_ID


# ============================================================
# Ayarlar Diyaloğu
# ============================================================

class SettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("Sysha v1.0 — Ayarlar")
        self.setMinimumWidth(580)
        self.setMinimumHeight(680)
        self.setStyleSheet(DARK_DIALOG_QSS)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setStyleSheet("background-color: #1e1e2e; color: #cdd6f4;")
        layout = QVBoxLayout(inner)

        # --- HF Tokenlar ---
        hf_group = QGroupBox("Hugging Face Token(lar)")
        hf_layout = QVBoxLayout(hf_group)
        hf_layout.addWidget(QLabel("Her satıra bir token (birden fazla desteklenir):"))
        self.tokens_edit = QTextEdit()
        self.tokens_edit.setPlaceholderText("hf_xxxx...\nhf_yyyy...")
        self.tokens_edit.setMaximumHeight(70)
        tokens = list(config.get("hf_tokens") or [])
        old = config.get("hf_token", "").strip()
        if old and old not in tokens:
            tokens.insert(0, old)
        self.tokens_edit.setPlainText("\n".join(tokens))
        hf_layout.addWidget(self.tokens_edit)
        layout.addWidget(hf_group)

        # --- Modeller ---
        model_group = QGroupBox("Modeller (sırayla denenir)")
        model_layout = QVBoxLayout(model_group)
        self.models_edit = QTextEdit()
        self.models_edit.setMaximumHeight(90)
        models = config.get("models") or DEFAULT_CONFIG["models"]
        self.models_edit.setPlainText("\n".join(models))
        model_layout.addWidget(self.models_edit)
        quick = QHBoxLayout()
        for m in RECOMMENDED_MODELS[:4]:
            short = m.split("/")[-1]
            btn = QPushButton(short)
            btn.setObjectName("secondary")
            btn.setStyleSheet("padding: 4px 8px; font-size: 11px;")
            btn.clicked.connect(lambda checked, model=m: self._append_model(model))
            quick.addWidget(btn)
        model_layout.addLayout(quick)
        layout.addWidget(model_group)

        # --- Üretim ---
        gen_group = QGroupBox("Üretim Ayarları")
        gen_form = QFormLayout(gen_group)
        self.max_tokens_spin = QSpinBox()
        self.max_tokens_spin.setRange(1, 100000)
        self.max_tokens_spin.setValue(int(config.get("max_tokens", 1024)))
        self.max_tokens_spin.setSingleStep(64)
        self.max_tokens_spin.setToolTip("Model yanıt uzunluğu üst sınırı")
        gen_form.addRow("Max Tokens:", self.max_tokens_spin)
        self.temp_spin = QDoubleSpinBox()
        self.temp_spin.setRange(0.0, 2.0)
        self.temp_spin.setSingleStep(0.05)
        self.temp_spin.setDecimals(3)
        self.temp_spin.setValue(float(config.get("temperature", 0.75)))
        gen_form.addRow("Temperature:", self.temp_spin)
        self.top_p_spin = QDoubleSpinBox()
        self.top_p_spin.setRange(0.0, 1.0)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setDecimals(3)
        self.top_p_spin.setValue(float(config.get("top_p", 0.9)))
        gen_form.addRow("Top P:", self.top_p_spin)
        layout.addWidget(gen_group)

        # --- Karakter ---
        char_group = QGroupBox("Karakter")
        char_form = QFormLayout(char_group)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(1, 5000)
        self.size_spin.setValue(int(config.get("character_size", DEFAULT_CHARACTER_SIZE)))
        self.size_spin.setSingleStep(8)
        self.size_spin.setToolTip("Karakter görseli boyutu (px). Sınır yok; istediğin değeri gir.")
        char_form.addRow("Karakter Boyutu (px):", self.size_spin)
        self.pose_hold_spin = QSpinBox()
        self.pose_hold_spin.setRange(0, 600000)
        self.pose_hold_spin.setValue(int(config.get("pose_hold_ms", 8000)))
        self.pose_hold_spin.setSingleStep(500)
        self.pose_hold_spin.setSuffix(" ms")
        self.pose_hold_spin.setToolTip("Duygu pozu bu süre sonra normal'e döner")
        char_form.addRow("Poz Tutma Süresi:", self.pose_hold_spin)
        layout.addWidget(char_group)

        # --- Input (karakter boyutundan bağımsız) ---
        input_group = QGroupBox("Input (mesaj kutusu) — karakter boyutundan bağımsız")
        input_form = QFormLayout(input_group)
        self.input_h_spin = QSpinBox()
        self.input_h_spin.setRange(1, 500)
        self.input_h_spin.setValue(int(config.get("input_height", 40)))
        self.input_h_spin.setSuffix(" px")
        input_form.addRow("Input Yüksekliği:", self.input_h_spin)
        self.input_font_spin = QSpinBox()
        self.input_font_spin.setRange(1, 200)
        self.input_font_spin.setValue(int(config.get("input_font_size", 13)))
        self.input_font_spin.setSuffix(" pt")
        input_form.addRow("Input Yazı Boyutu:", self.input_font_spin)
        self.input_w_spin = QSpinBox()
        self.input_w_spin.setRange(0, 5000)
        self.input_w_spin.setValue(int(config.get("input_width", 0)))
        self.input_w_spin.setSuffix(" px")
        self.input_w_spin.setSpecialValueText("Otomatik")
        self.input_w_spin.setToolTip("0 = otomatik (pencere genişliğine yayılır). Aksi halde sabit min. genişlik.")
        input_form.addRow("Input Min. Genişlik:", self.input_w_spin)
        layout.addWidget(input_group)

        # --- Balon ---
        bubble_group = QGroupBox("Konuşma Balonu")
        bubble_form = QFormLayout(bubble_group)
        self.bubble_font_spin = QSpinBox()
        self.bubble_font_spin.setRange(1, 200)
        self.bubble_font_spin.setValue(int(config.get("bubble_font_size", 13)))
        self.bubble_font_spin.setSuffix(" pt")
        bubble_form.addRow("Balon Yazı Boyutu:", self.bubble_font_spin)
        self.bubble_op_spin = QSpinBox()
        self.bubble_op_spin.setRange(0, 255)
        self.bubble_op_spin.setValue(int(config.get("bubble_opacity", 235)))
        bubble_form.addRow("Balon Opaklığı (0-255):", self.bubble_op_spin)
        self.bubble_w_spin = QSpinBox()
        self.bubble_w_spin.setRange(1, 5000)
        self.bubble_w_spin.setValue(int(config.get("bubble_max_width", 360)))
        self.bubble_w_spin.setSuffix(" px")
        bubble_form.addRow("Balon Max Genişlik:", self.bubble_w_spin)
        self.bubble_timeout_spin = QSpinBox()
        self.bubble_timeout_spin.setRange(0, 600000)
        self.bubble_timeout_spin.setValue(int(config.get("bubble_timeout_ms", 14000)))
        self.bubble_timeout_spin.setSingleStep(500)
        self.bubble_timeout_spin.setSuffix(" ms")
        self.bubble_timeout_spin.setToolTip("0 = balonlar otomatik kaybolmaz")
        bubble_form.addRow("Balon Görünürlük Süresi:", self.bubble_timeout_spin)
        self.max_bubbles_spin = QSpinBox()
        self.max_bubbles_spin.setRange(1, 50)
        self.max_bubbles_spin.setValue(int(config.get("max_visible_bubbles", 4)))
        bubble_form.addRow("Max Görünür Balon:", self.max_bubbles_spin)
        self.bubble_pad_y_spin = QSpinBox()
        self.bubble_pad_y_spin.setRange(0, 200)
        self.bubble_pad_y_spin.setValue(int(config.get("bubble_padding_y", BUBBLE_PAD_Y)))
        self.bubble_pad_y_spin.setSuffix(" px")
        self.bubble_pad_y_spin.setToolTip("Üst ve alt boşluk aynı değer (eşit)")
        bubble_form.addRow("Balon Üst/Alt Boşluk:", self.bubble_pad_y_spin)
        self.bubble_pad_x_spin = QSpinBox()
        self.bubble_pad_x_spin.setRange(0, 200)
        self.bubble_pad_x_spin.setValue(int(config.get("bubble_padding_x", BUBBLE_PAD_X)))
        self.bubble_pad_x_spin.setSuffix(" px")
        bubble_form.addRow("Balon Sol/Sağ Boşluk:", self.bubble_pad_x_spin)
        layout.addWidget(bubble_group)

        # --- Typewriter / animasyon ---
        tw_group = QGroupBox("Yazı Animasyonu (Typewriter)")
        tw_form = QFormLayout(tw_group)
        self.tw_ms_spin = QSpinBox()
        self.tw_ms_spin.setRange(0, 500)
        self.tw_ms_spin.setValue(int(config.get("typewriter_ms", 26)))
        self.tw_ms_spin.setSuffix(" ms")
        self.tw_ms_spin.setToolTip("Harf başına gecikme. 0 = anında yazılır.")
        tw_form.addRow("Harf Gecikmesi:", self.tw_ms_spin)
        self.next_pause_spin = QSpinBox()
        self.next_pause_spin.setRange(0, 60000)
        self.next_pause_spin.setValue(int(config.get("next_pause_ms", 650)))
        self.next_pause_spin.setSingleStep(50)
        self.next_pause_spin.setSuffix(" ms")
        self.next_pause_spin.setToolTip("![next:next] ile bölünen balonlar arası bekleme")
        tw_form.addRow("Balonlar Arası Pause:", self.next_pause_spin)
        self.tw_sound_cb = QCheckBox("Typewriter tık sesi")
        self.tw_sound_cb.setChecked(bool(config.get("typewriter_sound", True)))
        tw_form.addRow(self.tw_sound_cb)
        layout.addWidget(tw_group)

        # --- Pencere ---
        win_group = QGroupBox("Pencere")
        win_form = QFormLayout(win_group)
        screens = QApplication.screens()
        self.screen_combo = QComboBox()
        for i, s in enumerate(screens):
            geo = s.geometry()
            self.screen_combo.addItem(f"Ekran {i} ({geo.width()}x{geo.height()})", i)
        self.screen_combo.setCurrentIndex(
            min(config.get("window", {}).get("screen", 0), max(0, len(screens) - 1))
        )
        win_form.addRow("Ekran:", self.screen_combo)
        self.always_top = QCheckBox("Her zaman üstte")
        self.always_top.setChecked(config.get("window", {}).get("always_on_top", True))
        win_form.addRow(self.always_top)
        self.opacity_spin = QDoubleSpinBox()
        self.opacity_spin.setRange(0.05, 1.0)
        self.opacity_spin.setSingleStep(0.05)
        self.opacity_spin.setDecimals(2)
        self.opacity_spin.setValue(float(config.get("window", {}).get("opacity", 1.0)))
        self.opacity_spin.setToolTip("Pencere şeffaflığı (1.0 = tamamen opak)")
        win_form.addRow("Pencere Opaklığı:", self.opacity_spin)
        layout.addWidget(win_group)

        # --- Çalışma promptu (araçlar / etiketler / kurallar) ---
        work_group = QGroupBox("Çalışma Promptu (duygu, balon, kurallar)")
        work_layout = QVBoxLayout(work_group)
        work_hint = QLabel(
            "Sistemin nasıl çalışacağı: duygu etiketleri, balon bölme, dil vb. "
            "Kişilikten ayrı tutulur."
        )
        work_hint.setWordWrap(True)
        work_hint.setStyleSheet("color: #a6adc8; font-size: 11px;")
        work_layout.addWidget(work_hint)
        self.work_prompt_edit = QTextEdit()
        self.work_prompt_edit.setPlainText(
            config.get("work_prompt") or DEFAULT_CONFIG["work_prompt"]
        )
        self.work_prompt_edit.setMinimumHeight(110)
        work_layout.addWidget(self.work_prompt_edit)
        layout.addWidget(work_group)

        # --- Kişilik promptu ---
        persona_group = QGroupBox("Kişilik Promptu (konuşma tarzı, karakter)")
        persona_layout = QVBoxLayout(persona_group)
        persona_hint = QLabel(
            "Kim olduğu, nasıl konuştuğu, üslup, düşünce tarzı. "
            "İstediğin gibi özelleştir."
        )
        persona_hint.setWordWrap(True)
        persona_hint.setStyleSheet("color: #a6adc8; font-size: 11px;")
        persona_layout.addWidget(persona_hint)
        self.personality_prompt_edit = QTextEdit()
        # Geriye uyumluluk: eski system_prompt varsa kişilik olarak göster
        persona_text = (
            (config.get("personality_prompt") or "").strip()
            or (config.get("system_prompt") or "").strip()
            or DEFAULT_CONFIG["personality_prompt"]
        )
        self.personality_prompt_edit.setPlainText(persona_text)
        self.personality_prompt_edit.setMinimumHeight(120)
        persona_layout.addWidget(self.personality_prompt_edit)
        layout.addWidget(persona_group)

        # --- Dinamik görüntü eklentisi ---
        dyn_group = QGroupBox("Dinamik Görüntü Eklentisi")
        dyn_layout = QVBoxLayout(dyn_group)
        self.dynamic_image_cb = QCheckBox("Dinamik görüntü açık (AI duygu yerine prompt üretir)")
        self.dynamic_image_cb.setChecked(bool(config.get("dynamic_image_enabled", False)))
        self.dynamic_image_cb.setToolTip(
            "Açıkken ![emotion:...] içine hazır isim değil, görsel düzenleme promptu yazılır. "
            "normal.png taban alınır, HF image-edit modelleriyle işlenir."
        )
        dyn_layout.addWidget(self.dynamic_image_cb)
        lim_row = QHBoxLayout()
        lim_row.addWidget(QLabel("Yanıt başına max dinamik görsel:"))
        self.max_dyn_img_spin = QSpinBox()
        self.max_dyn_img_spin.setRange(1, 20)
        self.max_dyn_img_spin.setValue(int(config.get("max_dynamic_images", 3)))
        self.max_dyn_img_spin.setToolTip(
            "Her AI yanıtında en fazla kaç farklı dinamik görsel üretilsin. "
            "Token/API tasarrufu için düşük tut; AI bu limiti görür."
        )
        lim_row.addWidget(self.max_dyn_img_spin)
        lim_row.addStretch()
        dyn_layout.addLayout(lim_row)
        dyn_layout.addWidget(QLabel("Görsel edit modelleri (sırayla denenir):"))
        self.image_models_edit = QTextEdit()
        self.image_models_edit.setMaximumHeight(70)
        img_models = config.get("image_edit_models") or DEFAULT_CONFIG["image_edit_models"]
        self.image_models_edit.setPlainText("\n".join(img_models))
        dyn_layout.addWidget(self.image_models_edit)
        layout.addWidget(dyn_group)

        # --- Hafıza ---
        mem_group = QGroupBox("Hafıza")
        mem_form = QFormLayout(mem_group)
        self.max_hist_spin = QSpinBox()
        self.max_hist_spin.setRange(1, 10000)
        self.max_hist_spin.setValue(int(config.get("max_history", 24)))
        mem_form.addRow("Max Geçmiş Mesaj:", self.max_hist_spin)
        self.hist_thresh_spin = QSpinBox()
        self.hist_thresh_spin.setRange(1, 10000)
        self.hist_thresh_spin.setValue(int(config.get("history_summarize_threshold", 18)))
        self.hist_thresh_spin.setToolTip("Bu eşiği aşınca eski mesajlar özetlenir")
        mem_form.addRow("Özetleme Eşiği:", self.hist_thresh_spin)
        layout.addWidget(mem_group)

        scroll.setWidget(inner)
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(scroll)

        brand_row = QHBoxLayout()
        brand_lbl = QLabel(f"Syshanbur  ·  {CHARACTER_NAME} Desktop")
        brand_lbl.setObjectName("brand")
        brand_lbl.setCursor(QCursor(Qt.PointingHandCursor))
        brand_lbl.setToolTip(SYSHANBUR_URL)
        brand_lbl.mousePressEvent = lambda e: QDesktopServices.openUrl(QUrl(SYSHANBUR_URL))
        brand_row.addWidget(brand_lbl)
        brand_row.addStretch()
        site_btn = QPushButton("Syshanbur sitesi ↗")
        site_btn.setObjectName("linkBtn")
        site_btn.setCursor(QCursor(Qt.PointingHandCursor))
        site_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(SYSHANBUR_URL)))
        brand_row.addWidget(site_btn)
        main_layout.addLayout(brand_row)

        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Kaydet")
        save_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("İptal")
        cancel_btn.setObjectName("secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        main_layout.addLayout(btn_layout)

    def _append_model(self, model: str):
        current = self.models_edit.toPlainText().strip()
        lines = [l.strip() for l in current.splitlines() if l.strip()]
        if model not in lines:
            lines.append(model)
            self.models_edit.setPlainText("\n".join(lines))

    def get_config(self) -> dict:
        cfg = self.config.copy()
        raw_tokens = self.tokens_edit.toPlainText().splitlines()
        tokens = [t.strip() for t in raw_tokens if t.strip()]
        cfg["hf_tokens"] = tokens
        cfg["hf_token"] = tokens[0] if tokens else ""

        raw_models = self.models_edit.toPlainText().splitlines()
        models = [m.strip() for m in raw_models if m.strip()]
        cfg["models"] = models if models else list(DEFAULT_CONFIG["models"])

        cfg["max_tokens"] = self.max_tokens_spin.value()
        cfg["temperature"] = self.temp_spin.value()
        cfg["top_p"] = self.top_p_spin.value()
        cfg["character_size"] = self.size_spin.value()
        cfg["pose_hold_ms"] = self.pose_hold_spin.value()
        cfg["input_height"] = self.input_h_spin.value()
        cfg["input_font_size"] = self.input_font_spin.value()
        cfg["input_width"] = self.input_w_spin.value()
        cfg["bubble_font_size"] = self.bubble_font_spin.value()
        cfg["bubble_opacity"] = self.bubble_op_spin.value()
        cfg["bubble_max_width"] = self.bubble_w_spin.value()
        cfg["bubble_timeout_ms"] = self.bubble_timeout_spin.value()
        cfg["max_visible_bubbles"] = self.max_bubbles_spin.value()
        cfg["bubble_padding_y"] = self.bubble_pad_y_spin.value()
        cfg["bubble_padding_x"] = self.bubble_pad_x_spin.value()
        cfg["typewriter_ms"] = self.tw_ms_spin.value()
        cfg["next_pause_ms"] = self.next_pause_spin.value()
        cfg["typewriter_sound"] = self.tw_sound_cb.isChecked()
        cfg["window"] = dict(cfg.get("window") or {})
        cfg["window"]["screen"] = self.screen_combo.currentData()
        cfg["window"]["always_on_top"] = self.always_top.isChecked()
        cfg["window"]["opacity"] = self.opacity_spin.value()
        cfg["work_prompt"] = self.work_prompt_edit.toPlainText().strip()
        cfg["personality_prompt"] = self.personality_prompt_edit.toPlainText().strip()
        # Eski alan: kişilikle senkron (eski sürümler / dış araçlar)
        cfg["system_prompt"] = cfg["personality_prompt"]
        cfg["max_history"] = self.max_hist_spin.value()
        cfg["history_summarize_threshold"] = self.hist_thresh_spin.value()
        cfg["dynamic_image_enabled"] = self.dynamic_image_cb.isChecked()
        cfg["max_dynamic_images"] = self.max_dyn_img_spin.value()
        raw_img = self.image_models_edit.toPlainText().splitlines()
        cfg["image_edit_models"] = [m.strip() for m in raw_img if m.strip()] or list(DEFAULT_CONFIG["image_edit_models"])
        return cfg


class SetupDialog(SettingsDialog):
    def __init__(self, config: dict, parent=None):
        super().__init__(config, parent)
        self.setWindowTitle("Sysha — İlk Kurulum")
        info = QLabel(
            f"Hoş geldin! Ben {CHARACTER_NAME} — Syshanbur masaüstü yoldaşın.\n"
            "Devam için en az bir Hugging Face API token gir.\n"
            "Token: https://huggingface.co/settings/tokens  (Read yetkisi yeterli)"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #f9e2af; margin-bottom: 8px;")
        # layout'un en üstüne ekle
        self.layout().insertWidget(0, info)


# ============================================================
# Ana Pencere
# ============================================================

class DesktopWaifu(QMainWindow):
    def __init__(self):
        super().__init__()
        log.info("Ana pencere oluşturuluyor")
        self.config = load_config()
        self.history: List[Dict] = []
        self.current_character = self.config.get("current_character") or DEFAULT_CHARACTER_ID
        self.current_season = self.config.get("current_season", "default")
        self.current_state = "normal"
        self._assets_dir = character_assets_dir(self.config)
        self._prompt_emotion_dir = character_prompt_emotion_dir(self.config)
        self.drag_pos: Optional[QPoint] = None
        self.chat_worker: Optional[ChatWorker] = None
        self.speech_worker: Optional[SpeechWorker] = None
        self.image_worker: Optional[ImageEditWorker] = None
        self._image_queue: List[str] = []
        self._image_busy = False
        self._dynamic_pixmaps: Dict[str, QPixmap] = {}
        self._pregen_mode = False
        self._pending_segments: List[dict] = []
        self._pregen_remaining: set = set()
        self.is_listening = False
        # Typewriter
        self._tw_segments: List[dict] = []
        self._tw_seg_index = 0
        self._tw_char_index = 0
        self._tw_cue_index = 0
        self._tw_generation = 0
        self._tw_timer = QTimer(self)
        self._tw_timer.timeout.connect(self._typewriter_tick)
        self._tw_pause_timer = QTimer(self)
        self._tw_pause_timer.setSingleShot(True)
        self._tw_pause_timer.timeout.connect(self._advance_segment)
        self._sound_effect = None
        self._chars_since_sound = 0

        self._setup_window()
        self._build_ui()
        self._load_images()
        self._apply_position()
        self._setup_tray()
        self._setup_sound()

        QTimer.singleShot(150, self._startup_flow)

        self.bubble_timer = QTimer(self)
        self.bubble_timer.setSingleShot(True)
        self.bubble_timer.timeout.connect(self._hide_bubble)
        log.info("Ana pencere hazır")

    def _startup_flow(self):
        """Token kontrolü → Karakter (isteğe bağlı) → Sezon seçimi → hazır."""
        tokens = self._get_tokens()
        if not tokens:
            log.info("HF token yok – kurulum")
            dlg = SetupDialog(self.config, self)
            if dlg.exec_() == QDialog.Accepted:
                self.config = dlg.get_config()
                if not save_config(self.config):
                    QMessageBox.critical(self, "Kaydetme Hatası", f"Ayarlar yazılamadı.\n{LOG_FILE}")
                self._reload_from_config()
            else:
                QMessageBox.warning(self, "Kurulum Gerekli", "API token olmadan devam edilemez.")
                QApplication.quit()
                return

        # Birden fazla karakter varsa seçim sun
        chars = get_characters(self.config)
        if len(chars) > 1:
            char_dlg = CharacterSelectDialog(self.config, self)
            if char_dlg.exec_() == QDialog.Accepted:
                cid = char_dlg.get_character_id()
                self._apply_character(cid, reload_history=False)
            else:
                self._apply_character(
                    self.config.get("current_character") or DEFAULT_CHARACTER_ID,
                    reload_history=False,
                )
        else:
            self._apply_character(
                self.config.get("current_character") or DEFAULT_CHARACTER_ID,
                reload_history=False,
            )

        # Sezon seç
        season_dlg = SeasonSelectDialog(self.config, self, character_id=self.current_character)
        if season_dlg.exec_() == QDialog.Accepted:
            season = season_dlg.get_season()
            self.current_season = season
            self.config["current_season"] = season
            if season not in (self.config.get("seasons") or []):
                self.config.setdefault("seasons", []).append(season)
            save_config(self.config)
            self.history = load_season_history(season, self.current_character)
            self.history = optimize_history(
                self.history,
                max_keep=int(self.config.get("max_history", 24)),
                threshold=int(self.config.get("history_summarize_threshold", 18))
            )
            log.info(
                "Sezon yüklendi: %s | karakter=%s | %d mesaj",
                season, self.current_character, len(self.history),
            )
        else:
            self.current_season = "default"
            self.history = load_season_history("default", self.current_character)

    def _stop_active_workers(self):
        """Karakter/sezon değişiminde çalışan işleri kes."""
        try:
            self._tw_timer.stop()
            self._tw_pause_timer.stop()
            self.bubble_timer.stop()
        except Exception:
            pass
        self._pregen_mode = False
        self._pending_segments = []
        self._pregen_remaining = set()
        self._image_queue = []
        self._image_busy = False
        if self.chat_worker and self.chat_worker.isRunning():
            try:
                self.chat_worker.finished.disconnect()
            except Exception:
                pass
            self.chat_worker = None
        if self.image_worker and self.image_worker.isRunning():
            try:
                self.image_worker.finished.disconnect()
            except Exception:
                pass
            self.image_worker = None
        try:
            self.send_btn.setEnabled(True)
            self.mic_btn.setEnabled(True)
        except Exception:
            pass

    def _apply_character(self, character_id: str, reload_history: bool = True):
        """Aktif karakteri değiştir: assets, prompt yolları, görseller, hafıza."""
        chars = get_characters(self.config)
        # config'e geri yaz (get_characters bazen kopya üretebilir)
        self.config["characters"] = chars
        if character_id not in chars:
            character_id = DEFAULT_CHARACTER_ID

        prev = getattr(self, "current_character", None)
        self.current_character = character_id
        self.config["current_character"] = character_id

        # Karakter bazlı son sezon
        ch = chars.get(character_id) or {}
        last_season = (ch.get("last_season") or "").strip() or "default"
        if reload_history:
            self.current_season = last_season
            self.config["current_season"] = last_season

        self._assets_dir = resolve_assets_path(ch.get("assets_dir") or "assets")
        self._prompt_emotion_dir = self._assets_dir / "prompt_emotions"
        try:
            self._prompt_emotion_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        self._dynamic_pixmaps = {}
        self._stop_active_workers()
        self._load_images()

        ch_info = get_current_character(self.config)
        title = f"{ch_info.get('name') or CHARACTER_NAME} Desktop"
        self.setWindowTitle(title)
        if hasattr(self, "tray") and self.tray is not None:
            self.tray.setToolTip(f"{title} — Syshanbur")

        if reload_history:
            self.history = load_season_history(self.current_season, self.current_character)
            self.history = optimize_history(
                self.history,
                max_keep=int(self.config.get("max_history", 24)),
                threshold=int(self.config.get("history_summarize_threshold", 18)),
            )
            self._clear_bubbles()
            self._set_state("normal")

        # last_season güncelle
        try:
            self.config["characters"][character_id]["last_season"] = self.current_season
        except Exception:
            pass

        save_config(self.config)
        log.info(
            "Karakter aktif: %s (önceki=%s) | assets=%s | sezon=%s | mesaj=%d",
            character_id, prev, self._assets_dir, self.current_season, len(self.history),
        )

    def _change_character(self):
        """Sağ tık / tray: karakter seç veya yönet."""
        # Mevcut konuşmayı bu karaktere kaydet
        try:
            chars = get_characters(self.config)
            if self.current_character in chars:
                chars[self.current_character]["last_season"] = self.current_season
            self.config["characters"] = chars
        except Exception:
            pass
        save_season_history(
            self.current_season, self.history, character_id=self.current_character
        )
        save_config(self.config)

        dlg = CharacterSelectDialog(self.config, self)
        result = dlg.exec_()
        # Diyalog içinde ekleme/düzenleme config'i değiştirmiş olabilir — her durumda kaydet
        self.config["characters"] = get_characters(self.config)
        save_config(self.config)

        if result != QDialog.Accepted:
            # İptal: yine de yeni eklenen karakterler kalsın, aktif karakter değişmesin
            # Ama assets düzenlendiyse mevcut karakteri yenile
            self._apply_character(self.current_character, reload_history=False)
            return

        cid = dlg.get_character_id()
        if not cid:
            cid = DEFAULT_CHARACTER_ID
        self._apply_character(cid, reload_history=True)
        ch = get_current_character(self.config)
        self._show_bubble(
            f"🎭 {ch.get('name') or cid}  ·  sezon: {self.current_season}  ·  {len(self.history)} mesaj"
        )

    def _setup_sound(self):
        ensure_tick_sound()
        if not SOUND_AVAILABLE or not TICK_SOUND_PATH.exists():
            return
        try:
            self._sound_effect = QSoundEffect(self)
            self._sound_effect.setSource(QUrl.fromLocalFile(str(TICK_SOUND_PATH.resolve())))
            self._sound_effect.setVolume(0.35)
        except Exception as e:
            log.warning("Ses yüklenemedi: %s", e)
            self._sound_effect = None

    def _setup_window(self):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.config.get("window", {}).get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("Sysha Desktop")
        size = int(self.config.get("character_size", DEFAULT_CHARACTER_SIZE))
        input_h = int(self.config.get("input_height", 40))
        input_w = int(self.config.get("input_width", 0) or 0)
        w = size + 40
        if input_w > 0:
            w = max(w, input_w + 24)
        self.resize(w, size + input_h + 100)
        try:
            op = float(self.config.get("window", {}).get("opacity", 1.0))
            self.setWindowOpacity(max(0.05, min(1.0, op)))
        except Exception:
            pass

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet("background: transparent;")
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 4, 6, 4)
        main_layout.setSpacing(0)
        main_layout.addStretch(1)

        self.bubble_container = QWidget()
        self.bubble_container.setStyleSheet("background: transparent;")
        self.bubble_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.bubble_layout = QVBoxLayout(self.bubble_container)
        self.bubble_layout.setContentsMargins(0, 0, 0, 6)
        self.bubble_layout.setSpacing(6)
        self.bubble_layout.setAlignment(Qt.AlignBottom | Qt.AlignHCenter)
        self.bubbles: List[QLabel] = []
        self.active_bubble: Optional[QLabel] = None
        main_layout.addWidget(self.bubble_container, 0, Qt.AlignBottom)

        self.bottom_block = QWidget()
        self.bottom_block.setStyleSheet("background: transparent;")
        bottom_layout = QVBoxLayout(self.bottom_block)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        self.char_label = QLabel()
        self.char_label.setAlignment(Qt.AlignCenter | Qt.AlignBottom)
        self.char_label.setStyleSheet("background: transparent;")
        self.char_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        bottom_layout.addWidget(self.char_label, 0, Qt.AlignHCenter)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            "color: #a6adc8; font-size: 10px; background: transparent; padding: 0; margin: 0;"
        )
        self.status_label.setFixedHeight(14)
        self.status_label.hide()
        bottom_layout.addWidget(self.status_label)

        input_h = int(self.config.get("input_height", 40))
        font_sz = int(self.config.get("input_font_size", 13))

        input_frame = QFrame()
        input_frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(17, 17, 27, 240);
                border-radius: 12px;
                border: 1px solid #313244;
                margin: 0;
                min-height: {input_h}px;
            }}
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(6, 4, 6, 4)
        input_layout.setSpacing(4)
        self.input_frame = input_frame

        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Mesaj yaz...")
        self.input_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: #cdd6f4;
                font-size: {font_sz}px;
                padding: 4px;
            }}
        """)
        self.input_edit.returnPressed.connect(self._send_text)
        input_layout.addWidget(self.input_edit)

        self.send_btn = QPushButton("➤")
        self.send_btn.setFixedSize(36, 32)
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #89b4fa; color: #1e1e2e;
                border: none; border-radius: 8px; font-size: 16px; font-weight: bold;
            }
            QPushButton:hover { background-color: #b4befe; }
            QPushButton:disabled { background-color: #45475a; }
        """)
        self.send_btn.clicked.connect(self._send_text)
        input_layout.addWidget(self.send_btn)

        self.mic_btn = QPushButton("🎤")
        self.mic_btn.setFixedSize(36, 32)
        self.mic_btn.setCheckable(True)
        self.mic_btn.setStyleSheet("""
            QPushButton {
                background-color: #45475a; color: #cdd6f4;
                border: none; border-radius: 8px; font-size: 14px;
            }
            QPushButton:hover { background-color: #585b70; }
            QPushButton:checked { background-color: #f38ba8; color: #1e1e2e; }
        """)
        self.mic_btn.clicked.connect(self._toggle_voice)
        input_layout.addWidget(self.mic_btn)

        self.settings_btn = QPushButton("⚙️")
        self.settings_btn.setFixedSize(36, 32)
        self.settings_btn.setToolTip("Ayarlar")
        self.settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #45475a; color: #cdd6f4;
                border: none; border-radius: 8px; font-size: 14px;
            }
            QPushButton:hover { background-color: #585b70; }
        """)
        self.settings_btn.clicked.connect(self._open_settings)
        input_layout.addWidget(self.settings_btn)

        bottom_layout.addWidget(input_frame, 0, Qt.AlignHCenter)
        main_layout.addWidget(self.bottom_block, 0, Qt.AlignBottom)

        self._anchor_bottom: Optional[int] = None
        self._in_pin = False
        QTimer.singleShot(0, self._capture_anchor_bottom)
        # Başlangıçta input genişlik/yükseklik ayarını uygula
        QTimer.singleShot(0, self._apply_input_style)

    def _bubble_pad(self) -> tuple:
        """Üst/alt ve sol/sağ padding (eşit dikey boşluk)."""
        py = int(self.config.get("bubble_padding_y", BUBBLE_PAD_Y))
        px = int(self.config.get("bubble_padding_x", BUBBLE_PAD_X))
        # Eski sabitlerle uyum: BUBBLE_PAD_Y toplam dikeydi; şimdi her kenar için yarı
        # Config değerleri "her kenar" anlamında kullanılır.
        return max(0, px), max(0, py)

    def _bubble_style(self) -> str:
        op = int(self.config.get("bubble_opacity", 235))
        fs = int(self.config.get("bubble_font_size", 13))
        px, py = self._bubble_pad()
        # Üst ve alt padding aynı (py), sol ve sağ aynı (px)
        return f"""
            QLabel {{
                background-color: rgba(17, 17, 27, {op});
                color: #cdd6f4;
                border: 1px solid #45475a;
                border-radius: 12px;
                padding: {py}px {px}px;
                font-size: {fs}px;
                font-family: 'Segoe UI', 'Inter', 'Arial', sans-serif;
                margin: 0px;
            }}
        """

    def _load_images(self):
        self.pixmaps = {}
        self._dynamic_pixmaps = {}
        size = int(self.config.get("character_size", DEFAULT_CHARACTER_SIZE))
        assets = getattr(self, "_assets_dir", None) or character_assets_dir(self.config)
        self._assets_dir = assets
        self._prompt_emotion_dir = assets / "prompt_emotions"
        for state in sorted(VALID_EMOTIONS):
            path = assets / f"{state}.png"
            if path.exists():
                pix = QPixmap(str(path))
                self.pixmaps[state] = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            else:
                log.warning("Görsel eksik: %s (%s)", path.name, assets)
        fallback = self.pixmaps.get("normal")
        if fallback is None:
            pix = QPixmap(size, size)
            pix.fill(QColor(0, 0, 0, 0))
            fallback = pix
            self.pixmaps["normal"] = fallback
        for state in VALID_EMOTIONS:
            if state not in self.pixmaps:
                self.pixmaps[state] = fallback
        self._set_state("normal")
        self.char_label.setFixedHeight(size + 4)
        if hasattr(self, "input_frame"):
            self._fit_window_to_content()
        else:
            self.resize(size + 36, size + 120)
        log.info("Karakter görselleri yüklendi (boyut=%d, assets=%s)", size, assets)

    def _set_state(self, state: str):
        self.current_state = state
        if state in self._dynamic_pixmaps:
            self.char_label.setPixmap(self._dynamic_pixmaps[state])
            return
        key = (state or "").strip().lower()
        if key in self.pixmaps:
            self.char_label.setPixmap(self.pixmaps[key])
            return
        if "normal" in self.pixmaps:
            self.char_label.setPixmap(self.pixmaps["normal"])

    def _apply_position(self):
        screens = QApplication.screens()
        screen_idx = self.config.get("window", {}).get("screen", 0)
        if screen_idx >= len(screens):
            screen_idx = 0
        geo = screens[screen_idx].availableGeometry()
        w = self.width()
        h = self.height()
        cfg_x = self.config.get("window", {}).get("x", -1)
        cfg_y = self.config.get("window", {}).get("y", -1)
        if cfg_x < 0:
            x = geo.x() + geo.width() - w - 30
        else:
            x = geo.x() + cfg_x
        if cfg_y < 0:
            y = geo.y() + (geo.height() - h) // 2
        else:
            y = geo.y() + cfg_y
        self.move(x, y)
        self._capture_anchor_bottom()

    def _setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.tray.setToolTip("Sysha Desktop — Syshanbur")
        menu = QMenu()
        show_action = QAction("Göster / Gizle", self)
        show_action.triggered.connect(self._toggle_visibility)
        settings_action = QAction("Ayarlar", self)
        settings_action.triggered.connect(self._open_settings)
        char_action = QAction("Karakter Değiştir", self)
        char_action.triggered.connect(self._change_character)
        season_action = QAction("Sezon Değiştir", self)
        season_action.triggered.connect(self._change_season)
        site_action = QAction("Syshanbur Sitesi", self)
        site_action.triggered.connect(lambda: QDesktopServices.openUrl(QUrl(SYSHANBUR_URL)))
        quit_action = QAction("Çıkış", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(show_action)
        menu.addAction(settings_action)
        menu.addAction(char_action)
        menu.addAction(season_action)
        menu.addSeparator()
        menu.addAction(site_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self._toggle_visibility() if r == QSystemTrayIcon.Trigger else None
        )
        self.tray.show()

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()

    def _get_tokens(self) -> List[str]:
        tokens = list(self.config.get("hf_tokens") or [])
        old = (self.config.get("hf_token") or "").strip()
        if old and old not in tokens:
            tokens.insert(0, old)
        return [t for t in tokens if t.strip()]

    def _change_season(self):
        # Mevcut sezonu kaydet
        save_season_history(
            self.current_season, self.history, character_id=self.current_character
        )
        dlg = SeasonSelectDialog(self.config, self, character_id=self.current_character)
        if dlg.exec_() == QDialog.Accepted:
            season = dlg.get_season()
            self.current_season = season
            self.config["current_season"] = season
            try:
                chars = get_characters(self.config)
                if self.current_character in chars:
                    chars[self.current_character]["last_season"] = season
                self.config["characters"] = chars
            except Exception:
                pass
            save_config(self.config)
            self.history = load_season_history(season, self.current_character)
            self.history = optimize_history(
                self.history,
                max_keep=int(self.config.get("max_history", 24))
            )
            self._clear_bubbles()
            self._show_bubble(f"Sezon: {season} ({len(self.history)} mesaj)")
            log.info("Sezon değiştirildi → %s (karakter=%s)", season, self.current_character)

    def _open_settings(self):
        dlg = SettingsDialog(self.config, self)
        if dlg.exec_() == QDialog.Accepted:
            self.config = dlg.get_config()
            if save_config(self.config):
                self._reload_from_config()
                QMessageBox.information(self, "Kaydedildi", "Ayarlar güncellendi.")
            else:
                self._reload_from_config()
                QMessageBox.critical(
                    self, "Kaydetme Hatası",
                    "Ayarlar diske yazılamadı (sadece bu oturum geçerli).\n"
                    f"Log: {LOG_FILE}"
                )

    def _reload_from_config(self):
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.config.get("window", {}).get("always_on_top", True):
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()
        self._load_images()
        self._apply_position()
        # Input: karakter boyutundan bağımsız kendi ayarları
        self._apply_input_style()
        # Pencere opaklığı
        try:
            op = float(self.config.get("window", {}).get("opacity", 1.0))
            self.setWindowOpacity(max(0.05, min(1.0, op)))
        except Exception:
            pass

    def _apply_input_style(self):
        """Input yüksekliği / yazı boyutu / genişlik — karakter boyutuna bağlı değil."""
        if not hasattr(self, "input_frame") or self.input_frame is None:
            return
        input_h = max(1, int(self.config.get("input_height", 40)))
        font_sz = max(1, int(self.config.get("input_font_size", 13)))
        input_w = int(self.config.get("input_width", 0) or 0)

        self.input_frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(24, 24, 37, 230);
                border-radius: 10px; border: 1px solid #45475a;
                margin: 0; min-height: {input_h}px;
            }}
        """)
        self.input_edit.setStyleSheet(f"""
            QLineEdit {{
                background: transparent; border: none; color: #cdd6f4;
                font-size: {font_sz}px; padding: 4px;
            }}
        """)
        self.input_frame.setFixedHeight(input_h)

        if input_w > 0:
            # Sabit genişlik: pencere genişliğine yayılmaz, ortalanır
            self.input_frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            self.input_frame.setMinimumWidth(input_w)
            self.input_frame.setMaximumWidth(input_w)
            self.input_frame.setFixedWidth(input_w)
        else:
            # Otomatik: pencere genişliğine yayılır
            self.input_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.input_frame.setMinimumWidth(0)
            self.input_frame.setMaximumWidth(16777215)
            # fixed width kilidini kaldır
            self.input_frame.setMinimumHeight(input_h)
            self.input_frame.setMaximumHeight(input_h)

        self._fit_window_to_content()

    def _fit_window_to_content(self):
        """Genişlik + yükseklik; alt kenar sabit."""
        char_size = max(1, int(self.config.get("character_size", DEFAULT_CHARACTER_SIZE)))
        input_w = int(self.config.get("input_width", 0) or 0)
        base_w = char_size + 36
        if input_w > 0:
            base_w = max(base_w, input_w + 24)
        self._relayout_upward(width=base_w)

    # ---------- Mesaj ----------

    def _send_text(self):
        text = self.input_edit.text().strip()
        if not text:
            return
        self.input_edit.clear()
        self._process_user_message(text)

    def _process_user_message(self, text: str):
        if self.chat_worker and self.chat_worker.isRunning():
            log.warning("Önceki sohbet hâlâ çalışıyor")
            return

        self._set_state("think")
        self.send_btn.setEnabled(False)
        self.mic_btn.setEnabled(False)

        self.history.append({"role": "user", "content": text})
        max_h = int(self.config.get("max_history", 24))
        self.history = optimize_history(self.history, max_keep=max_h)
        save_season_history(
            self.current_season, self.history, character_id=self.current_character
        )

        messages: List[Dict] = []
        work = character_work_prompt(self.config)
        ch_info = get_current_character(self.config)
        ch_name = ch_info.get("name") or CHARACTER_NAME
        if bool(self.config.get("dynamic_image_enabled", False)):
            max_dyn = max(1, int(self.config.get("max_dynamic_images", 3)))
            dyn_rules = """# DİNAMİK GÖRÜNTÜ MODU — PROFESYONEL GÖRSEL YÖNLENDİRME

**Bu mod aktifken aşağıdaki kurallar zorunludur.**

* Bu yanıtta en fazla **{n} farklı `![emotion:...]` etiketi** kullan. Benzersiz etiket sayısı {n} değerini aşamaz.
* Hazır duygu adlarını (`happy`, `sad`, `angry` vb.) tek başına kullanma. Her etiketin içine, karakterin o anki duygusunu ve beden dilini tanımlayan **35–80 kelimelik, profesyonel ve ayrıntılı İngilizce görsel yönlendirme prompt'u** yaz.
* Her prompt; yüz ifadesini (gözler, kaşlar, ağız, allık ve bakış yönü), kafa açısını, omuzları, kolları, elleri, parmakları, gövde duruşunu, ağırlık merkezini ve genel silueti açıkça tanımlamalıdır.
* Stil: **anime illustration, clean line art, expressive pose, consistent character design.** Oyunculuk abartılı, okunaklı ve görsel olarak ayırt edilebilir olmalıdır.
* **{cname}** karakter kimliğini koru: saç modeli, kıyafet, vücut oranları ve ayırt edici özellikleri her prompt'ta tutarlı kalmalıdır.
* Her prompt tek satır olmalı; etiketin içine satır sonu koyma. İngilizce, görsel üretim ve image-edit modellerinin doğrudan anlayabileceği somut ifadeler kullan.
* Her balonda duygu etiketi kullanmak zorunda değilsin. Yalnızca görsel ifadenin değiştiği veya belirgin bir oyunculuk gerektiği durumlarda ekle.
* Aynı görsel ifade devam ediyorsa gereksiz yere yeni etiket üretme. Etiket sayısı sınırını aşma.
* Etiketleri yalnızca `![emotion:...]` biçiminde yaz. Açıklama, ek metin veya duygu adı ekleme.

**Örnek:**

`![emotion:anime girl with a wide bright smile, sparkling crescent-shaped eyes, softly raised eyebrows, deep pink blush on her cheeks, head tilted slightly to the right, shoulders relaxed and open, both arms bent with hands clasped in front of her chest, fingers interlaced, upper body leaning forward, balanced weight distribution, lively and expressive silhouette, anime illustration, clean line art, consistent character design]`

**Öncelik:** Görsel prompt'ları kısa duygu etiketleri değil, karakterin yüzünü ve tüm bedenini yönlendiren profesyonel oyunculuk talimatlarıdır. Her etiket, karakterin mevcut ruh hâlini görsel olarak açık ve tutarlı biçimde yansıtmalıdır.
""".format(n=max_dyn, cname=ch_name)
            work = (work + "\n\n" + dyn_rules) if work else dyn_rules
        persona = character_personality_prompt(self.config)
        system_parts = []
        if work:
            system_parts.append("[ÇALIŞMA KURALLARI]\n" + work)
        if persona:
            system_parts.append("[KİŞİLİK]\n" + persona)
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        messages.extend(self.history)

        models = self.config.get("models") or list(DEFAULT_CONFIG["models"])
        tokens = self._get_tokens()
        max_tokens = int(self.config.get("max_tokens", 1024))
        temperature = float(self.config.get("temperature", 0.75))

        top_p = float(self.config.get("top_p", 0.9))
        self.chat_worker = ChatWorker(
            tokens=tokens, models=models, messages=messages,
            max_tokens=max_tokens, temperature=temperature, top_p=top_p, parent=self
        )
        self.chat_worker.finished.connect(self._on_chat_finished)
        self.chat_worker.start()

    def _on_chat_finished(self, response: str, success: bool):
        self.send_btn.setEnabled(True)
        self.mic_btn.setEnabled(True)

        if not success:
            self._set_state("normal")
            self._start_typewriter([{"text": f"⚠️ {response}", "cues": []}])
            return

        # Geçmişe ETİKETLİ kaydet — model formatı (emotion/next) unutmasın.
        # Kullanıcıya gösterilen metin typewriter yolunda strip_all_tags ile temizlenir.
        for_history = _normalize_spaces(response or "")
        self.history.append({"role": "assistant", "content": for_history})
        save_season_history(
            self.current_season, self.history, character_id=self.current_character
        )

        visible = self._visible_text(response)
        if not visible.strip():
            self._set_state("normal")
            return

        segments = parse_response_to_segments(
            self._keep_only_display_tags(response)
        )
        for seg in segments:
            # Sadece balon metninden etiketleri çıkar; cues zaten parse edildi
            seg["text"] = strip_all_tags(seg.get("text") or "")
        segments = [s for s in segments if (s.get("text") or "").strip()]
        if not segments:
            self._set_state("normal")
            return

        # Dinamik mod: önce tüm emotion görsellerini üret, sonra yaz
        if bool(self.config.get("dynamic_image_enabled", False)):
            self._pregen_dynamic_then_speak(segments)
        else:
            self._start_typewriter(segments)

    def _keep_only_display_tags(self, text: str) -> str:
        """Sadece emotion ve next etiketlerini bırak (gösterim/parse için)."""
        return text or ""

    def _visible_text(self, text: str) -> str:
        """Kullanıcının göreceği etiketsiz metin."""
        return strip_all_tags(self._keep_only_display_tags(text))

    # ---------- Bubble / Typewriter (orijinal mantık korundu) ----------

    def sizeHint(self):
        # Qt'nin çocuk widget sizeHint'ine göre pencereyi şişirmesini engelle
        return self.size() if self.width() > 0 else super().sizeHint()

    def minimumSizeHint(self):
        return QSize(80, 80)

    def _capture_anchor_bottom(self):
        """Karakter+input bloğunun ekrandaki alt kenarını kaydet (tek gerçek kaynak)."""
        geo = self.frameGeometry()
        self._anchor_bottom = int(geo.y() + geo.height())

    def _screen_avail(self):
        screen = QApplication.screenAt(self.frameGeometry().center()) or QApplication.primaryScreen()
        return screen.availableGeometry() if screen else None

    def _content_height(self) -> int:
        """Balonlar + karakter + input için gereken toplam yükseklik."""
        bubble_h = 0
        if self.bubbles:
            bubble_h = sum(max(int(b.height()), 1) for b in self.bubbles)
            bubble_h += self.bubble_layout.spacing() * max(0, len(self.bubbles) - 1)
            m = self.bubble_layout.contentsMargins()
            bubble_h += m.top() + m.bottom() + 4
        char_h = int(self.config.get("character_size", DEFAULT_CHARACTER_SIZE)) + 4
        input_h = max(1, int(self.config.get("input_height", 40))) if hasattr(self, "input_frame") else 40
        # margins + status + küçük pay
        chrome = 24
        return char_h + input_h + chrome + bubble_h

    def _pin_to_anchor(self, width: int = None, height: int = None):
        """
        Pencereyi verilen boyuta getir; alt kenar her zaman _anchor_bottom'da kalsın.
        Qt/WM kaydırsa bile son adımda tekrar hizalanır.
        """
        if self._in_pin:
            return
        self._in_pin = True
        try:
            self.__pin_to_anchor_impl(width, height)
        finally:
            self._in_pin = False

    def __pin_to_anchor_impl(self, width: int = None, height: int = None):
        if self._anchor_bottom is None:
            self._capture_anchor_bottom()
        bottom = int(self._anchor_bottom)
        w = int(width if width is not None else self.width())
        h = int(height if height is not None else self.height())
        w = max(80, w)
        h = max(80, h)

        avail = self._screen_avail()
        if avail is not None:
            top_limit = int(avail.y())
            bot_limit = int(avail.y() + avail.height())
            # Anchor ekran dışındaysa içeri al (sürükleme/çoklu monitör)
            if bottom > bot_limit:
                bottom = bot_limit
                self._anchor_bottom = bottom
            if bottom - h < top_limit:
                h = max(80, bottom - top_limit)
            y = bottom - h
            if y < top_limit:
                y = top_limit
                h = max(80, bottom - y)
        else:
            y = bottom - h

        x = int(self.x())
        # Fixed size: layout-driven otomatik büyümeyi tamamen kes
        self.setMinimumSize(80, 80)
        self.setMaximumSize(16777215, 16777215)
        self.setFixedSize(w, h)
        self.move(x, int(y))

        # WM / DPI sapması: bir frame sonra alt kenarı zorla düzelt
        QTimer.singleShot(0, lambda b=bottom, ww=w: self._force_bottom(b, ww))

    def _force_bottom(self, bottom: int, width: int = None):
        try:
            if not self.isVisible():
                return
            w = int(width if width is not None else self.width())
            h = int(self.height())
            y = int(bottom - h)
            avail = self._screen_avail()
            if avail is not None and y < avail.y():
                y = int(avail.y())
                h = max(80, int(bottom - y))
                self.setFixedSize(w, h)
            if self.y() != y or self.x() != int(self.x()):
                self.move(int(self.x()), y)
            # Gerçek alt kenar hâlâ sapmışsa son kez
            actual = self.frameGeometry().y() + self.frameGeometry().height()
            if abs(actual - bottom) > 1:
                self.move(int(self.x()), int(bottom - self.frameGeometry().height()))
        except Exception as e:
            log.debug("_force_bottom: %s", e)

    def _bubble_width(self) -> int:
        # Balon genişliği config'ten; karakter boyutuna zorunlu bağlı değil
        max_w = int(self.config.get("bubble_max_width", 360))
        return max(1, max_w)

    def _measure_text_height(self, text: str, width: int, font: Optional[QFont] = None) -> int:
        if not text:
            px, py = self._bubble_pad()
            return max(20, py * 2 + 10)
        if font is None:
            fs = int(self.config.get("bubble_font_size", 13))
            font = QFont("Segoe UI", fs)
        fm = QFontMetrics(font)
        px, py = self._bubble_pad()
        # Sol+sağ padding + ince border
        inner_w = max(20, width - (px * 2) - 2)
        flags = int(Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter)
        rect = fm.boundingRect(0, 0, inner_w, 4000, flags, text)
        # Üst + alt padding eşit (py + py) + border
        return max(py * 2 + 10, rect.height() + (py * 2) + 2)

    def _grow_bubble_for_text(self, lbl: QLabel, text: str):
        if lbl is None:
            return
        clean = (text or "").rstrip()
        w = self._bubble_width()
        lbl.setFixedWidth(w)
        lbl.setWordWrap(True)
        lbl.setText(clean)
        h = self._measure_text_height(clean, w, lbl.font())
        old_h = lbl.height()
        if h != old_h:
            lbl.setFixedHeight(max(h, 20))
            self._relayout_upward()
        elif old_h < 20:
            lbl.setFixedHeight(max(h, 20))
            self._relayout_upward()

    def _fade_bubbles(self):
        n = len(self.bubbles)
        for i, b in enumerate(self.bubbles):
            age = n - 1 - i
            opacity = {0: 1.0, 1: 0.88, 2: 0.75}.get(age, 0.62)
            try:
                eff = b.graphicsEffect()
                if not isinstance(eff, QGraphicsOpacityEffect):
                    eff = QGraphicsOpacityEffect(b)
                    b.setGraphicsEffect(eff)
                eff.setOpacity(opacity)
            except Exception:
                pass
        if self.bubbles:
            self.active_bubble = self.bubbles[-1]

    def _relayout_upward(self, width: int = None):
        """
        İçerik yüksekliğine göre pencereyi ayarla.
        Alt kenar (_anchor_bottom) ASLA aşağı inmez — sadece yukarı büyür / yukarıdan küçülür.
        """
        try:
            if self._anchor_bottom is None:
                self._capture_anchor_bottom()
            need_h = self._content_height()
            w = int(width) if width is not None else int(self.width())
            self._pin_to_anchor(width=w, height=need_h)
        except Exception as e:
            log.error("_relayout_upward: %s", e)

    def _clear_bubbles(self, animated: bool = False):
        """Balonları kaldır. animated=True ise fade-out ile siler."""
        if not self.bubbles:
            self.active_bubble = None
            return
        if not animated:
            for b in list(self.bubbles):
                try:
                    self.bubble_layout.removeWidget(b)
                    b.deleteLater()
                except Exception:
                    pass
            self.bubbles.clear()
            self.active_bubble = None
            self._relayout_upward()
            return
        # Layout'tan HEMEN çıkar (eski balonlar yer kaplamasın → aşağı şişme olmasın)
        bubbles = list(self.bubbles)
        self.bubbles.clear()
        self.active_bubble = None
        for b in bubbles:
            try:
                self.bubble_layout.removeWidget(b)
                b.hide()
                b.deleteLater()
            except Exception:
                pass
        self._relayout_upward()

    def _new_bubble(self) -> QLabel:
        lbl = QLabel()
        lbl.setWordWrap(True)
        lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lbl.setStyleSheet(self._bubble_style())
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        w = self._bubble_width()
        lbl.setFixedWidth(w)
        lbl.setFixedHeight(30)
        self.bubble_layout.addWidget(lbl, 0, Qt.AlignHCenter)
        self.bubbles.append(lbl)
        self.active_bubble = lbl
        lbl.show()
        while len(self.bubbles) > max(1, int(self.config.get("max_visible_bubbles", MAX_VISIBLE_BUBBLES))):
            old = self.bubbles.pop(0)
            try:
                self.bubble_layout.removeWidget(old)
                old.deleteLater()
            except Exception:
                pass
        self._fade_bubbles()
        self._relayout_upward()
        return lbl

    def _set_bubble_text(self, text: str):
        if self.active_bubble is None:
            self._new_bubble()
        self._grow_bubble_for_text(self.active_bubble, text or "")

    def _start_typewriter(self, segments: List[dict]):
        self._tw_timer.stop()
        self._tw_pause_timer.stop()
        self.bubble_timer.stop()
        # Yeni mesaj gelince eskileri animasyonlu sil (aniden kaybolmasın)
        self._clear_bubbles(animated=True)
        self._tw_generation += 1
        self._tw_segments = segments or [{"text": "", "cues": []}]
        self._tw_seg_index = 0
        self._tw_char_index = 0
        self._tw_cue_index = 0
        self._chars_since_sound = 0
        if not self._tw_segments:
            return
        self._new_bubble()
        self._apply_cues_at(0)
        interval = max(0, int(self.config.get("typewriter_ms", 26)))
        if interval <= 0:
            # Anında tüm metni yaz
            while self._current_segment() is not None:
                seg = self._current_segment()
                full = seg.get("text") or ""
                self._tw_char_index = len(full)
                if self.active_bubble is not None:
                    self._grow_bubble_for_text(self.active_bubble, full)
                self._apply_cues_at(self._tw_char_index)
                if self._tw_seg_index + 1 < len(self._tw_segments):
                    self._tw_seg_index += 1
                    self._tw_char_index = 0
                    self._tw_cue_index = 0
                    self._new_bubble()
                    self._apply_cues_at(0)
                else:
                    self._finish_typewriter()
                    return
            self._finish_typewriter()
            return
        self._tw_timer.start(interval)

    def _current_segment(self) -> Optional[dict]:
        if 0 <= self._tw_seg_index < len(self._tw_segments):
            return self._tw_segments[self._tw_seg_index]
        return None


    def _collect_emotion_prompts(self, segments: List[dict]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for seg in segments or []:
            for c in seg.get("cues") or []:
                p = (c.get("emotion") or "").strip()
                if not p:
                    continue
                key = p.lower()
                # Klasik tek kelimelik duygu — üretme
                if key in VALID_EMOTIONS and " " not in p and "," not in p:
                    continue
                if p not in seen:
                    seen.add(p)
                    ordered.append(p)
        return ordered

    def _pregen_dynamic_then_speak(self, segments: List[dict]):
        """Önce tüm dinamik görselleri üret; bitince typewriter başlat."""
        self._pending_segments = segments
        prompts = self._collect_emotion_prompts(segments)
        max_dyn = max(1, int(self.config.get("max_dynamic_images", 3)))
        if len(prompts) > max_dyn:
            log.info("Dinamik görsel limiti: %d -> %d (fazlasi atlandi)", len(prompts), max_dyn)
            prompts = prompts[:max_dyn]
        ped = getattr(self, "_prompt_emotion_dir", None) or character_prompt_emotion_dir(self.config)
        needed: List[str] = []
        for p in prompts:
            if p in self._dynamic_pixmaps:
                continue
            cached = _find_cached_emotion_path(p, base_dir=ped)
            if cached is not None:
                self._load_dynamic_pixmap(p, cached, apply=False)
                continue
            needed.append(p)

        if not needed:
            log.info("Dinamik görseller hazır (cache), yanıt gösteriliyor")
            self._start_typewriter(segments)
            return

        log.info("Dinamik pregen: %d görsel üretilecek", len(needed))
        self._pregen_mode = True
        self._pregen_remaining = set(needed)
        self._image_queue = list(needed)
        self._image_busy = False
        if "think" in self.pixmaps:
            self.char_label.setPixmap(self.pixmaps["think"])
        # Kullanıcıya kısa bilgi
        self._show_bubble(f"🎨 İfadeler hazırlanıyor ({len(needed)})…")
        self.send_btn.setEnabled(False)
        self.mic_btn.setEnabled(False)
        self._pump_image_queue()

    def _request_dynamic_emotion(self, prompt: str):
        """Typewriter sırasında: sadece cache'den göster (üretim pregen'de bitti)."""
        prompt = (prompt or "").strip()
        if not prompt:
            return
        key = prompt.lower()
        if key in VALID_EMOTIONS and key in self.pixmaps and " " not in prompt and "," not in prompt:
            self._set_state(key)
            return
        if prompt in self._dynamic_pixmaps:
            self._set_state(prompt)
            return
        ped = getattr(self, "_prompt_emotion_dir", None) or character_prompt_emotion_dir(self.config)
        cached = _find_cached_emotion_path(prompt, base_dir=ped)
        if cached is not None:
            self._load_dynamic_pixmap(prompt, cached, apply=True)
            return
        # Henüz yoksa normal / think
        if "normal" in self.pixmaps:
            self.char_label.setPixmap(self.pixmaps["normal"])

    def _pump_image_queue(self):
        if self._image_busy:
            return
        if not self._image_queue:
            if self._pregen_mode and not self._pregen_remaining:
                self._finish_pregen()
            return
        if self.image_worker and self.image_worker.isRunning():
            self._image_busy = True
            return
        prompt = self._image_queue.pop(0)
        assets = getattr(self, "_assets_dir", None) or character_assets_dir(self.config)
        ped = getattr(self, "_prompt_emotion_dir", None) or (assets / "prompt_emotions")
        base = assets / "normal.png"
        cached = _find_cached_emotion_path(prompt, base_dir=ped)
        if cached is not None:
            self._load_dynamic_pixmap(prompt, cached, apply=False)
            self._pregen_remaining.discard(prompt)
            self._pump_image_queue()
            return
        out_path = ped / _prompt_cache_key(prompt)
        tokens = self._get_tokens()
        models = self.config.get("image_edit_models") or list(DEFAULT_CONFIG["image_edit_models"])
        self._image_busy = True
        self.image_worker = ImageEditWorker(
            tokens=tokens,
            models=models,
            prompt=prompt,
            base_image_path=base,
            out_path=out_path,
            parent=self,
        )
        try:
            self.image_worker.finished.disconnect()
        except Exception:
            pass
        self.image_worker.finished.connect(self._on_image_edit_finished)
        self.image_worker.status.connect(lambda s: log.info("ImageEdit status: %s", s))
        self.image_worker.start()

    def _load_dynamic_pixmap(self, prompt: str, path: Path, apply: bool = True):
        try:
            size = int(self.config.get("character_size", DEFAULT_CHARACTER_SIZE))
            pix = QPixmap(str(path))
            if pix.isNull():
                log.warning("Dinamik görsel okunamadı: %s", path)
                return
            pix = pix.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._dynamic_pixmaps[prompt] = pix
            if apply:
                self.current_state = prompt
                self.char_label.setPixmap(pix)
        except Exception as e:
            log.error("Dinamik pixmap yükleme: %s", e)

    def _on_image_edit_finished(self, prompt: str, path_or_err: str, success: bool):
        self._image_busy = False
        if success:
            self._load_dynamic_pixmap(prompt, Path(path_or_err), apply=not self._pregen_mode)
        else:
            log.warning("Dinamik görsel başarısız (%s): %s", prompt[:40], path_or_err)
        self._pregen_remaining.discard(prompt)
        if self._pregen_mode:
            left = len(self._pregen_remaining) + len(self._image_queue) + (1 if self._image_busy else 0)
            if self._image_queue or (self.image_worker and self.image_worker.isRunning()):
                self._show_bubble(f"🎨 İfadeler hazırlanıyor ({len(self._pregen_remaining)} kaldı)…")
            self._pump_image_queue()
            if not self._image_queue and not self._image_busy and not self._pregen_remaining:
                self._finish_pregen()
            return
        self._pump_image_queue()

    def _finish_pregen(self):
        if not self._pregen_mode:
            return
        self._pregen_mode = False
        segs = self._pending_segments or []
        self._pending_segments = []
        self._pregen_remaining = set()
        self.send_btn.setEnabled(True)
        self.mic_btn.setEnabled(True)
        log.info("Dinamik pregen bitti → yanıt gösteriliyor (%d segment)", len(segs))
        if segs:
            self._start_typewriter(segs)
        else:
            self._set_state("normal")

    def _apply_cues_at(self, char_index: int):
        seg = self._current_segment()
        if not seg:
            return
        cues = seg.get("cues") or []
        dynamic = bool(self.config.get("dynamic_image_enabled", False))
        while self._tw_cue_index < len(cues) and cues[self._tw_cue_index]["at"] <= char_index:
            name = cues[self._tw_cue_index]["emotion"]
            if dynamic:
                self._request_dynamic_emotion(name)
            else:
                key = (name or "").strip().lower()
                if key in self.pixmaps:
                    self._set_state(key)
                elif key in VALID_EMOTIONS and "normal" in self.pixmaps:
                    self._set_state("normal")
            self._tw_cue_index += 1

    def _typewriter_tick(self):
        seg = self._current_segment()
        if seg is None:
            self._finish_typewriter()
            return
        full = seg.get("text") or ""
        if self._tw_char_index >= len(full):
            if self.active_bubble is not None:
                self._grow_bubble_for_text(self.active_bubble, full)
            if self._tw_seg_index + 1 < len(self._tw_segments):
                self._tw_timer.stop()
                pause = int(self.config.get("next_pause_ms", 650))
                self._tw_pause_timer.start(pause)
            else:
                self._finish_typewriter()
            return
        self._tw_char_index += 1
        visible = full[:self._tw_char_index]
        if self.active_bubble is not None:
            self.active_bubble.setText(visible)
            if self._tw_char_index == 1 or self._tw_char_index % 2 == 0 or self._tw_char_index >= len(full):
                w = self._bubble_width()
                h = self._measure_text_height(visible, w, self.active_bubble.font())
                if h > self.active_bubble.height():
                    self.active_bubble.setFixedHeight(h)
                    self._relayout_upward()
        self._apply_cues_at(self._tw_char_index)
        ch = full[self._tw_char_index - 1]
        self._chars_since_sound += 1
        if (
            self.config.get("typewriter_sound", True)
            and self._sound_effect is not None
            and ch not in (" ", "\n", "\t")
            and self._chars_since_sound >= 2
        ):
            self._chars_since_sound = 0
            try:
                if not self._sound_effect.isPlaying():
                    self._sound_effect.play()
            except Exception:
                pass

    def _advance_segment(self):
        self._tw_seg_index += 1
        self._tw_char_index = 0
        self._tw_cue_index = 0
        self._chars_since_sound = 0
        self._new_bubble()
        self._apply_cues_at(0)
        interval = max(0, int(self.config.get("typewriter_ms", 26)))
        self._tw_timer.start(interval)

    def _finish_typewriter(self):
        self._tw_timer.stop()
        self._tw_pause_timer.stop()
        visible_segments = self._tw_segments[-len(self.bubbles):] if self.bubbles else []
        for lbl, seg in zip(self.bubbles, visible_segments):
            txt = (seg.get("text") or "").rstrip()
            self._grow_bubble_for_text(lbl, txt)
        timeout = int(self.config.get("bubble_timeout_ms", 14000))
        if timeout > 0:
            self.bubble_timer.start(timeout)
        hold = int(self.config.get("pose_hold_ms", 8000))
        if hold > 0:
            QTimer.singleShot(hold, lambda: self._set_state("normal"))

    def _show_bubble(self, text: str):
        self._tw_timer.stop()
        self._tw_pause_timer.stop()
        self.bubble_timer.stop()
        self._clear_bubbles(animated=True)
        # Fade biraz sürsün; yeni balonu kısa gecikmeyle aç
        def _after_fade():
            self._new_bubble()
            self._set_bubble_text(text or "")
            timeout = int(self.config.get("bubble_timeout_ms", 14000))
            if timeout > 0:
                self.bubble_timer.start(timeout)
        QTimer.singleShot(120, _after_fade)

    def _hide_bubble(self):
        self._clear_bubbles(animated=True)

    def _show_status(self, text: str):
        if text:
            log.debug("status: %s", text)
        self.status_label.hide()

    # ---------- Ses ----------

    def _toggle_voice(self):
        if self.is_listening:
            self._stop_listening()
        else:
            self._start_listening()

    def _start_listening(self):
        if not STT_AVAILABLE:
            QMessageBox.warning(
                self, "Eksik Paket",
                "Ses tanıma için:\npip install SpeechRecognition pyaudio"
            )
            self.mic_btn.setChecked(False)
            return
        if self.speech_worker and self.speech_worker.isRunning():
            return
        self.is_listening = True
        self.mic_btn.setChecked(True)
        self._set_state("think")
        self.speech_worker = SpeechWorker(self)
        self.speech_worker.finished.connect(self._on_speech_finished)
        self.speech_worker.status.connect(self._show_status)
        self.speech_worker.error.connect(self._on_speech_error)
        self.speech_worker.start()

    def _stop_listening(self):
        self.is_listening = False
        self.mic_btn.setChecked(False)
        if self.speech_worker:
            self.speech_worker.stop()
        self._set_state("normal")

    def _on_speech_finished(self, text: str):
        self.is_listening = False
        self.mic_btn.setChecked(False)
        if text.strip():
            self._process_user_message(text)

    def _on_speech_error(self, msg: str):
        self.is_listening = False
        self.mic_btn.setChecked(False)
        self._set_state("normal")
        self._show_bubble(f"🎤 {msg}")

    # ---------- Sürükle & Menü ----------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Qt/layout bazen alt kenarı kaydırır — geri pinle
        if self._in_pin or self._anchor_bottom is None or self.drag_pos is not None:
            return
        actual = self.frameGeometry().y() + self.frameGeometry().height()
        if abs(actual - int(self._anchor_bottom)) > 2:
            self._in_pin = True
            try:
                self.move(int(self.x()), int(self._anchor_bottom) - int(self.height()))
            finally:
                self._in_pin = False

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self.drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() == Qt.LeftButton and self.drag_pos is not None:
            self.move(event.globalPos() - self.drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.drag_pos = None
        self._capture_anchor_bottom()
        screens = QApplication.screens()
        screen_idx = self.config.get("window", {}).get("screen", 0)
        if screen_idx < len(screens):
            geo = screens[screen_idx].availableGeometry()
            self.config["window"]["x"] = self.x() - geo.x()
            self.config["window"]["y"] = self.y() - geo.y()
            save_config(self.config)

    def contextMenuEvent(self, event: QContextMenuEvent):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #11111b; color: #cdd6f4;
                border: 1px solid #313244; border-radius: 10px; padding: 8px;
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }
            QMenu::item { padding: 8px 22px; border-radius: 6px; }
            QMenu::item:selected { background-color: #89b4fa; color: #11111b; }
            QMenu::separator { height: 1px; background: #313244; margin: 6px 10px; }
        """)
        settings_act = menu.addAction("⚙️  Ayarlar")
        char_act = menu.addAction("🎭  Karakter Değiştir")
        season_act = menu.addAction("📁  Sezon Değiştir")
        reset_pos_act = menu.addAction("📍  Sağa Ortala")
        log_act = menu.addAction("📋  Logları Aç")
        site_act = menu.addAction("🌐  Syshanbur")
        hide_act = menu.addAction("👁️  Gizle")
        menu.addSeparator()
        quit_act = menu.addAction("❌  Çıkış")

        action = menu.exec_(event.globalPos())
        if action == settings_act:
            self._open_settings()
        elif action == char_act:
            self._change_character()
        elif action == season_act:
            self._change_season()
        elif action == site_act:
            QDesktopServices.openUrl(QUrl(SYSHANBUR_URL))
        elif action == reset_pos_act:
            self.config["window"]["x"] = -1
            self.config["window"]["y"] = -1
            save_config(self.config)
            self._apply_position()
        elif action == log_act:
            self._open_logs()
        elif action == hide_act:
            self.hide()
        elif action == quit_act:
            save_season_history(
                self.current_season, self.history, character_id=self.current_character
            )
            QApplication.quit()

    def _open_logs(self):
        try:
            if sys.platform == "win32":
                os.startfile(str(LOG_FILE))
            elif sys.platform == "darwin":
                os.system(f'open "{LOG_FILE}"')
            else:
                os.system(f'xdg-open "{LOG_FILE}"')
        except Exception as e:
            QMessageBox.information(self, "Log", f"Log konumu:\n{LOG_FILE}\n\n{e}")

    def closeEvent(self, event):
        save_season_history(
            self.current_season, self.history, character_id=self.current_character
        )
        if hasattr(self, "tray") and self.tray.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()


# ============================================================
# Giriş
# ============================================================

def _apply_dark_palette(app: QApplication):
    """QMessageBox / QInputDialog gibi sistem pencerelerinin beyaz kalmasını engelle."""
    app.setStyle("Fusion")
    palette = QPalette()
    bg = QColor("#1e1e2e")
    base = QColor("#313244")
    text = QColor("#cdd6f4")
    highlight = QColor("#89b4fa")
    palette.setColor(QPalette.Window, bg)
    palette.setColor(QPalette.WindowText, text)
    palette.setColor(QPalette.Base, base)
    palette.setColor(QPalette.AlternateBase, QColor("#181825"))
    palette.setColor(QPalette.Text, text)
    palette.setColor(QPalette.Button, base)
    palette.setColor(QPalette.ButtonText, text)
    palette.setColor(QPalette.Highlight, highlight)
    palette.setColor(QPalette.HighlightedText, QColor("#1e1e2e"))
    palette.setColor(QPalette.ToolTipBase, base)
    palette.setColor(QPalette.ToolTipText, text)
    palette.setColor(QPalette.Link, highlight)
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor("#6c7086"))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#6c7086"))
    app.setPalette(palette)
    app.setStyleSheet("""
        QMessageBox, QInputDialog {
            background-color: #1e1e2e; color: #cdd6f4;
        }
        QMessageBox QLabel, QInputDialog QLabel { color: #cdd6f4; }
        QMessageBox QPushButton, QInputDialog QPushButton {
            background-color: #89b4fa; color: #1e1e2e;
            border: none; border-radius: 6px; padding: 6px 14px; min-width: 70px;
            font-weight: bold;
        }
        QMessageBox QPushButton:hover, QInputDialog QPushButton:hover {
            background-color: #b4befe;
        }
        QInputDialog QLineEdit {
            background-color: #313244; color: #cdd6f4;
            border: 1px solid #45475a; border-radius: 6px; padding: 6px;
        }
        QToolTip {
            background-color: #313244; color: #cdd6f4;
            border: 1px solid #45475a; padding: 4px;
        }
    """)


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("Sysha Desktop")
    app.setOrganizationName("Syshanbur")
    _apply_dark_palette(app)

    ASSETS_DIR.mkdir(exist_ok=True)
    PROMPT_EMOTION_DIR.mkdir(parents=True, exist_ok=True)
    SEASONS_DIR.mkdir(exist_ok=True)

    def excepthook(exc_type, exc_value, exc_tb):
        log.critical("Yakalanmayan hata:\n%s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = excepthook

    window = DesktopWaifu()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()