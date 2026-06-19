# Kentsel Dönüşüm Karar Destek Aracı

Vatandaş veya müteahhitin, harita üzerinde parsel(leri) ve mevcut bina ayak
izini çizerek; TAKS/KAKS, kat sayısı, bağımsız bölüm sayısı, hak sahibi payı
ve yaklaşık maliyet/kâr hesabını görebildiği, önerilen yeni binayı 3B olarak
gösteren bir karar destek aracı.

Bu, earthquake-analytics deprem dashboard'undan bağımsız, ayrı bir araçtır
(aynı repo içinde, kendi backend/frontend'i ile).

## Mimari

- `backend/` — FastAPI tabanlı hesaplama API'si (`/calculate`).
  Hesaplama mantığı `calculations.py` içinde, mevzuattan bağımsız,
  basitleştirilmiş bir TAKS/KAKS/maliyet modelidir.
- `frontend/` — Tek sayfalık, build aracı gerektirmeyen HTML/JS uygulaması.
  [MapLibre GL JS](https://maplibre.org/) (ücretsiz, API anahtarı gerektirmez)
  ile 3B harita; [Turf.js](https://turfjs.org/) ile alan hesabı, parsel
  birleştirme (union) ve önerilen bina kütlesinin ölçeklenmesi.

## Nasıl Kullanılır

1. **Backend'i başlatın:**
   ```
   cd urban-transformation/backend
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```
   API `http://localhost:8000` adresinde çalışır (`/docs` üzerinden test edilebilir).

2. **Frontend'i açın:**
   `frontend/index.html` dosyasını doğrudan bir tarayıcıda açın (statik
   dosya, sunucu gerekmez). Sol panelde "Backend API adresi" alanı
   varsayılan olarak `http://localhost:8000`'i gösterir.

3. **Haritada çizim:**
   - "Parsel Çiz" ile parsel sınırlarını tıklayarak çizin, "Şekli Bitir"e
     basın. Birden çok parsel çizip "Parselleri Birleştir" ile (ada bazlı
     dönüşümde olduğu gibi) birleştirebilirsiniz.
   - "Bina Ayak İzi Çiz" ile mevcut bina(ların) ayak izini çizin.
   - Alanlar (m²) çizimden otomatik hesaplanır, formda görüntülenir ve
     gerekirse manuel düzeltilebilir.

4. **Form alanlarını doldurun:** mevcut kat sayısı, bağımsız bölüm/hak
   sahibi sayısı, hedef TAKS/KAKS (imar planına göre), hedef daire
   büyüklüğü, kat yüksekliği, m² inşaat maliyeti ve satış fiyatı.

5. **"Hesapla ve 3B Modeli Göster"** butonuna basın:
   - Backend'den TAKS/KAKS, önerilen kat sayısı, toplam inşaat alanı,
     hak sahibi/müteahhit bağımsız bölüm dağılımı ve yaklaşık
     maliyet/gelir/kâr hesabı döner.
   - Çizilen parsel/ayak izi, hesaplanan yeni ayak izi alanına göre
     ölçeklenip hesaplanan bina yüksekliğine ekstrüde edilerek (3B kütle)
     haritada gösterilir.

## Hesaplama Mantığı (özet)

- **Mevcut TAKS** = mevcut ayak izi / parsel alanı
- **Mevcut KAKS (emsal)** = (mevcut kat sayısı × mevcut ayak izi) / parsel alanı
- **Yeni ayak izi** = parsel alanı × hedef TAKS
- **Toplam inşaat alanı** = parsel alanı × hedef KAKS
- **Yeni kat sayısı** = ceil(toplam inşaat alanı / yeni ayak izi)
- **Toplam bağımsız bölüm tahmini** = toplam inşaat alanı / hedef ortalama
  daire büyüklüğü (en az hak sahibi sayısı kadar)
- **Hak sahibi / müteahhit payı** = bağımsız bölümler önce hak sahiplerine
  (1 birim/hak sahibi), kalanı müteahhide paylaştırılır
- **Maliyet** = toplam inşaat alanı × m² inşaat maliyeti
- **Gelir** = müteahhide kalan satılabilir alan × m² satış fiyatı
- **Kâr** = gelir − maliyet

> ⚠️ Bu hesaplamalar **tahminidir**. KDV, harç/ruhsat giderleri, kat
> karşılığı sözleşme şartları, güncel imar planı kısıtları, deprem
> risk/dönüşüm teşvikleri gibi etkenler dahil edilmemiştir. Resmi
> başvurularda ilgili belediye imar müdürlüğü ve mevzuat esas alınmalıdır.

## "3B Bina Modeli" Hakkında Önemli Not

Mevcut sürümde önerilen bina, **gerçek mimari/generative AI ile üretilmiş
bir mesh değil**; çizilen parsel/ayak izi geometrisinin hesaplanan alana
göre ölçeklenip hesaplanan yüksekliğe ekstrüde edilmesiyle oluşan
**parametrik bir kütle modelidir**. "AI destekli" gerçek 3B bina/mimari
model üretimi (örn. cephe, çekme mesafeleri, gerçekçi mimari detaylar)
ileride bir generative 3D model servisi (görselden/parametreden mesh
üreten bir API) entegre edilerek eklenebilir — bu, sonraki bir aşama
olarak planlanmalıdır.

## Yol Haritası (sonraki aşamalar)

1. Gerçek kadastro/imar verisi entegrasyonu (TKGM, belediye açık veri).
2. Birden fazla parsel/bina için optimizasyon (en uygun kat sayısı/kâr
   dengesi önerisi).
3. Gerçek generative AI tabanlı 3B bina/mimari model üretimi.
4. Deprem riski verisiyle ilişkilendirme (bu repodaki deprem
   dashboard'u ile entegrasyon — örn. risk skoruna göre dönüşüm önceliği).
5. Kullanıcı hesapları, proje kaydetme/paylaşma.
