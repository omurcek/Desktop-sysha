# Sysha Desktop v1.0

**Syshanbur masaüstü yoldaşı** — PyQt5 tabanlı, Hugging Face Inference API ile çalışan anime tarzı masaüstü sohbet uygulaması.

Sysha, ekranınızın kenarında yaşayan sevimli bir karakterdir. Yazışır, duygu ifadeleri gösterir, sesle dinler ve (isteğe bağlı) dinamik AI görselleriyle poz değiştirir. Birden fazla karakter ekleyebilir; her birinin kendi assets klasörü, promptları ve sohbet hafızası vardır.

| | |
|---|---|
| **Sürüm** | 1.0 |
| **Dil** | Python 3.9+ |
| **Arayüz** | PyQt5 |
| **LLM / Görsel** | Hugging Face Inference API |
| **Site** | [syshanbur.pythonanywhere.com](https://syshanbur.pythonanywhere.com) |

---

## Özellikler

- **Masaüstü companion arayüzü** — çerçevesiz, her zaman üstte, sürükle-bırak, sistem tepsisi
- **Duygu balonları** — `![emotion:…]` ve `![next:next]` ile parçalı, typewriter animasyonlu yanıtlar
- **Çoklu karakter** — varsayılan Sysha; kendi assets klasörünüzle yan karakter ekleme
- **Sezon (kalıcı hafıza)** — karakter bazlı sohbet geçmişi, özetleme
- **Hugging Face modelleri** — birden fazla token ve model yedekleme sırası
- **Ses girişi** — mikrofon ile Türkçe konuşma tanıma (opsiyonel)
- **Dinamik görüntü** — `normal.png` üzerinden image-edit ile anlık ifade üretimi (opsiyonel)
- **Özelleştirilebilir promptlar** — çalışma kuralları + kişilik; karakter assets’inden `work_prompt.txt` / `personality_prompt.txt`

---

## Hızlı başlangıç

### 1. Gereksinimler

- Python 3.9 veya üzeri
- [Hugging Face](https://huggingface.co/settings/tokens) hesabı ve **Read** yetkili API token

### 2. Bağımlılıklar

```bash
pip install PyQt5 huggingface_hub Pillow
```

İsteğe bağlı (ses girişi):

```bash
pip install SpeechRecognition pyaudio
```

> Windows’ta `pyaudio` için önceden derlenmiş wheel gerekebilir. Linux’ta `portaudio` geliştirme paketleri önerilir.

### 3. Assets klasörü

Uygulama dizininde `assets/` altında en az şu dosyalar olmalıdır:

```
assets/
  normal.png
  happy.png
  think.png
  angry.png
  relaxed.png
  sad.png
  shy.png
  sleepy.png
```

Şeffaf PNG, kare veya benzer en-boy oranı önerilir.

### 4. Çalıştırma

```bash
python sysha_desktop.py
```

İlk açılışta HF token istenir; ardından sezon seçilir. Token’ı [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) adresinden oluşturabilirsiniz.

---

## Klasör yapısı

```
proje/
├── sysha_desktop.py      # Ana uygulama
├── README.md
├── REHBER.md             # Detaylı kullanım rehberi
├── config.json           # Otomatik oluşur (ayarlar)
├── assets/               # Varsayılan karakter (Sysha) görselleri
│   ├── normal.png
│   ├── happy.png
│   ├── …
│   ├── type_tick.wav     # Yoksa otomatik üretilir
│   └── prompt_emotions/  # Dinamik görsel önbelleği
├── seasons/              # Sohbet hafızası (karakter bazlı alt klasörler)
│   └── sysha/
│       └── default.json
└── logs/
    └── desktop_waifu.log
```

---

## Arayüz özeti

| Kontrol | İşlev |
|---------|--------|
| **Mesaj kutusu + ➤** | Metin gönder |
| **🎤** | Sesle dinle (STT yüklüyse) |
| **🎭** | Karakter seç / ekle / düzenle |
| **⚙️** | Ayarlar (token, model, prompt, balon, pencere…) |
| **Sağ tık** | Karakter, sezon, konum, log, çıkış |
| **Sistem tepsisi** | Göster/gizle, ayarlar, karakter, sezon |

---

## Çoklu karakter

1. **🎭** veya Ayarlar → *Karakterler (çoklu)*  
2. **＋ Yeni Karakter** → ad + assets klasörü  
3. Klasörde `work_prompt.txt` / `personality_prompt.txt` varsa otomatik yüklenebilir  
4. **Seç** ile aktif karakter değişir  

Her karakterin kendi görselleri, promptları, dinamik görsel önbelleği ve `seasons/<id>/` hafızası vardır. Sysha varsayılan karakterdir ve silinemez.

Detaylar için **[REHBER.md](REHBER.md)** dosyasına bakın.

---

## Yapılandırma

Ayarlar arayüzden kaydedilir; `config.json` içinde tutulur. Önemli alanlar:

| Alan | Açıklama |
|------|----------|
| `hf_tokens` | Hugging Face token listesi |
| `models` | Sırayla denenen chat modelleri |
| `work_prompt` / `personality_prompt` | Global çalışma + kişilik (karakter override edebilir) |
| `characters` / `current_character` | Karakter listesi ve aktif id |
| `dynamic_image_enabled` | AI görsel ifade modu |
| `character_size`, `bubble_*`, `typewriter_ms` | Görünüm ve animasyon |

Yanıt protokolü: her balon `![emotion:…]` ile başlamalı; parçalar `![next:next]` ile ayrılır. Geçmişte etiketler **korunur** (model formatı unutmasın); ekranda kullanıcı yalnızca temiz metni görür.

---

## Lisans ve marka

Sysha / Syshanbur projesi kapsamında geliştirilmiştir.  
Site: [https://syshanbur.pythonanywhere.com](https://syshanbur.pythonanywhere.com)

Üçüncü taraf modeller ve Hugging Face API kendi kullanım koşullarına tabidir.

---

## Sorun giderme (kısa)

| Belirti | Olası çözüm |
|---------|-------------|
| Token hatası | Ayarlar → geçerli HF token; Read yetkisi |
| Görsel yok | `assets/*.png` dosyalarını kontrol edin |
| Ses çalışmıyor | `SpeechRecognition` + `pyaudio`; mikrofon izni |
| Model başarısız | `models` listesine alternatif ekleyin; token kotası |
| Log | `logs/desktop_waifu.log` |

Ayrıntılı kurulum, karakter ekleme ve prompt yazımı için **[REHBER.md](REHBER.md)** dosyasını okuyun.
