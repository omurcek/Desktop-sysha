# Sysha Desktop — Kullanım Rehberi

Bu rehber; kurulumu, günlük kullanımı, karakter eklemeyi, promptları ve gelişmiş ayarları adım adım anlatır.

---

## İçindekiler

1. [Kurulum](#1-kurulum)
2. [İlk çalıştırma](#2-ilk-çalıştırma)
3. [Günlük kullanım](#3-günlük-kullanım)
4. [Karakter sistemi](#4-karakter-sistemi)
5. [Sezonlar (hafıza)](#5-sezonlar-hafıza)
6. [Duygu etiketleri ve balonlar](#6-duygu-etiketleri-ve-balonlar)
7. [Promptlar](#7-promptlar)
8. [Dinamik görüntü modu](#8-dinamik-görüntü-modu)
9. [Ayarlar referansı](#9-ayarlar-referansı)
10. [Dosya ve klasörler](#10-dosya-ve-klasörler)
11. [Sorun giderme](#11-sorun-giderme)

---

## 1. Kurulum

### Python

Python **3.9+** önerilir.

```bash
python --version
```

### Paketler

Zorunlu:

```bash
pip install PyQt5 huggingface_hub Pillow
```

Ses girişi (isteğe bağlı):

```bash
pip install SpeechRecognition pyaudio
```

| Paket | Ne için |
|-------|---------|
| `PyQt5` | Arayüz |
| `huggingface_hub` | Chat + image-edit API |
| `Pillow` | Dinamik görsel (şeffaf PNG) |
| `SpeechRecognition` / `pyaudio` | Mikrofon |

### Hugging Face token

1. [https://huggingface.co/settings/tokens](https://huggingface.co/settings/tokens)  
2. Yeni token oluşturun (**Read** yeterli)  
3. İlk açılışta veya **Ayarlar → Hugging Face Token(lar)** alanına yapıştırın  

Birden fazla token satır satır yazılabilir; kota veya hata durumunda sırayla denenir.

### Assets (Sysha)

`sysha_desktop.py` ile aynı dizinde:

```
assets/
  normal.png    # zorunlu (yoksa boş şeffaf yedek)
  happy.png
  think.png
  angry.png
  relaxed.png
  sad.png
  shy.png
  sleepy.png
```

- Format: PNG, mümkünse **şeffaf arka plan**  
- Boyut: kare veya yakın oran (uygulama `character_size` ile ölçekler)

---

## 2. İlk çalıştırma

```bash
python sysha_desktop.py
```

Sıra:

1. **Token yoksa** → İlk kurulum penceresi (HF token + temel ayarlar)  
2. **Birden fazla karakter varsa** → Karakter seçimi  
3. **Sezon seçimi** → mevcut sezon veya yeni sohbet  

Pencere varsayılan olarak ekranın sağında, **her zaman üstte** ve çerçevesizdir. Sürükleyerek taşıyabilirsiniz; konum `config.json` içine kaydolur.

---

## 3. Günlük kullanım

### Kontroller

| Öğe | Açıklama |
|-----|----------|
| Metin kutusu | Enter veya **➤** ile gönder |
| **🎤** | Konuşmayı dinler (Google STT, `tr-TR`) |
| **🎭** | Karakter seç / ekle / düzenle / sil |
| **⚙️** | Tüm ayarlar |
| Sağ tık | Menü: karakter, sezon, sağa ortala, log, gizle, çıkış |
| Tepsi ikonu | Arka planda tut; tıkla göster/gizle |

### Sohbet akışı

1. Mesaj yazıp gönderirsiniz  
2. Karakter **think** pozuna geçer  
3. HF modelinden yanıt gelir  
4. Yanıt balonlara bölünür; typewriter ile yazılır; duygu görselleri değişir  
5. Bir süre sonra balonlar solabilir; poz `normal`e döner  

Çıkışta veya karakter değişiminde sohbet **sezon dosyasına** yazılır.

---

## 4. Karakter sistemi

### Varsayılan: Sysha

- Kimlik: `sysha`  
- Assets: `assets/`  
- Silinemez  

### Yeni karakter ekleme

1. **🎭** butonuna tıklayın  
2. **＋ Yeni Karakter**  
3. **Görünen ad** girin  
4. **Assets klasörü** seçin (göreli veya mutlak yol)  
5. İsteğe bağlı: **Assets’ten prompt dosyalarını yükle**  
6. **Kaydet** → listeden seçip **Seç**

Klasörde şu dosyalar aranır:

| Dosya | Kullanım |
|-------|----------|
| `normal.png` … `sleepy.png` | Duygu görselleri |
| `work_prompt.txt` | Çalışma kuralları (varsa forma dolar) |
| `personality_prompt.txt` | Kişilik (varsa forma dolar) |

### Prompt önceliği (karakter)

1. Karakter kaydındaki `work_prompt` / `personality_prompt` (config)  
2. Assets içindeki `.txt` dosyaları  
3. Global Ayarlar’daki promptlar  

### Karakter değiştirme

- **🎭** → listeden seç → **Seç**  
- Ayarlar → **Karakterler (çoklu)** → aynı diyalog  
- Sağ tık / tepsi → **Karakter Değiştir**  

Değişimde: görseller, prompt yolları ve o karaktere ait sezon hafızası yüklenir. Önceki karakterin sohbeti kaydedilir.

### Örnek assets düzeni (yan karakter)

```
karakterler/miku/
  normal.png
  happy.png
  think.png
  angry.png
  relaxed.png
  sad.png
  shy.png
  sleepy.png
  work_prompt.txt
  personality_prompt.txt
```

---

## 5. Sezonlar (hafıza)

Her **karakter + sezon** çifti ayrı geçmiş tutar.

Konum:

```
seasons/
  sysha/
    default.json
    okul.json
  miku/
    default.json
```

- **Sezon Değiştir** (sağ tık / tepsi): yeni sezon oluştur, sil, seç  
- Uzun geçmiş otomatik **özetlenir** (`max_history`, `history_summarize_threshold`)  
- Asistan mesajları geçmişte **etiketli** saklanır (model formatı bozulmasın diye); ekranda etiket görünmez  

---

## 6. Duygu etiketleri ve balonlar

Modelden beklenen format (work prompt ile zorunlu kılınır):

```text
![emotion:happy] Merhaba! Nasılsın? ![next:next] ![emotion:think] Bugün ne yaptın?
```

| Etiket | Anlam |
|--------|--------|
| `![emotion:normal]` | Nötr |
| `![emotion:happy]` | Mutlu |
| `![emotion:think]` | Düşünüyor |
| `![emotion:angry]` | Kızgın |
| `![emotion:relaxed]` | Rahat |
| `![emotion:sad]` | Üzgün |
| `![emotion:shy]` | Utangaç |
| `![emotion:sleepy]` | Uykulu |
| `![next:next]` | Sonraki balon |

- Kullanıcı yalnızca metni görür  
- Geçmişe etiketli metin yazılır  
- Dinamik modda `emotion:` içine uzun İngilizce görsel prompt yazılır (hazır duygu adı değil)

---

## 7. Promptlar

### İki katman

| Katman | Görev |
|--------|--------|
| **Çalışma promptu** | Etiketler, balon uzunluğu, dil, yasaklar |
| **Kişilik promptu** | Kim olduğu, üslup, samimiyet, “asistan gibi davranmama” |

Ayarlar’dan düzenlenir. Karakter bazlı override için assets `.txt` veya karakter formundaki alanlar kullanılır.

### İyi pratikler

- Çalışma kurallarını kişilikten ayırın  
- Karakter assets’ine özel `personality_prompt.txt` koyun  
- Çok uzun promptlar token tüketir; gereksiz tekrardan kaçının  

---

## 8. Dinamik görüntü modu

**Ayarlar → Dinamik Görüntü Eklentisi** ile açılır.

- Model, `![emotion:…]` içine hazır isim yerine **İngilizce sahne/poz promptu** yazar  
- `normal.png` taban alınır; HF **image-edit** modelleri ile işlenir  
- Sonuç şeffaf PNG olarak `assets/prompt_emotions/` (veya karakter assets’i altında) önbelleğe alınır  
- Benzer prompt’lar yeniden kullanılır  

Dikkat:

- Daha fazla API çağrısı ve süre  
- `max_dynamic_images` ile yanıt başına üst sınır  
- `Pillow` ve uygun image-edit model erişimi gerekir  

---

## 9. Ayarlar referansı

| Bölüm | Örnek alanlar |
|-------|----------------|
| HF Token(lar) | Birden fazla satır |
| Modeller | Sırayla denenen chat modelleri |
| Üretim | `max_tokens`, `temperature`, `top_p` |
| Karakter görünümü | Boyut (px), poz tutma süresi |
| Input | Yükseklik, yazı boyutu, min. genişlik |
| Balon | Yazı boyutu, opaklık, max genişlik, süre, padding |
| Typewriter | Harf gecikmesi, balon arası pause, tık sesi |
| Pencere | Ekran, her zaman üstte, opaklık |
| Promptlar | work + personality |
| Dinamik görüntü | Aç/kapa, limit, edit modelleri |
| Hafıza | max geçmiş, özet eşiği |

Kaydettikten sonra pencere ve görseller yenilenir.

---

## 10. Dosya ve klasörler

| Yol | Açıklama |
|-----|----------|
| `config.json` | Tüm ayarlar + karakter listesi |
| `assets/` | Sysha görselleri + varsayılan dinamik cache |
| `seasons/<karakter_id>/` | JSON sohbet geçmişleri |
| `logs/desktop_waifu.log` | Dönen log dosyası |

`config.json` silinirse varsayılanlarla yeniden oluşur; sezon dosyaları silinmezse sohbetler kalır.

---

## 11. Sorun giderme

### “Token tanımlı değil” / 401

- Token’ı Ayarlar’a tekrar girin  
- HF’de token’ın geçerli ve Read yetkili olduğunu kontrol edin  

### Karakter görseli boş / değişmiyor

- İlgili assets klasöründe `normal.png` var mı?  
- **🎭** ile doğru karakter seçili mi?  
- Log: `logs/desktop_waifu.log`  

### Model “tüm modeller başarısız”

- Model adlarını güncelleyin (HF’de chat uyumlu modeller)  
- Alternatif modelleri listeye ekleyin  
- Kota / ücretli model kısıtlarını kontrol edin  

### Mikrofon hatası

```bash
pip install SpeechRecognition pyaudio
```

- Sistem mikrofon izni  
- Linux: `portaudio19-dev` benzeri paketler  

### Dinamik görsel üretilmiyor

- `Pillow` kurulu mu?  
- Image-edit model erişimi ve token  
- `normal.png` mevcut mu?  

### Pencere kayboldu

- Sistem tepsisinden **Göster**  
- Sağ tık menüsü (pencere varken) → **Sağa Ortala**  

### Logları açma

Sağ tık → **Logları Aç** veya:

```
logs/desktop_waifu.log
```

---

## Hızlı kontrol listesi

- [ ] `pip install PyQt5 huggingface_hub Pillow`  
- [ ] HF token alındı  
- [ ] `assets/normal.png` (+ diğer duygular) hazır  
- [ ] `python sysha_desktop.py`  
- [ ] İsteğe bağlı: yan karakter assets + **🎭** ile ekleme  
- [ ] İsteğe bağlı: `work_prompt.txt` / `personality_prompt.txt`  

Daha kısa proje özeti için **[README.md](README.md)** dosyasına bakın.

---

*Sysha Desktop v1.0 — Syshanbur*
