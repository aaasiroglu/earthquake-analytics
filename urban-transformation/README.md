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

## MAKS / İBB Verisi İçe Aktarma

Nihai hedef, parsel/bina/nüfus/bağımsız bölüm verisinin manuel çizim yerine
**İBB'nin kendi GML ve MAKS (.shp) verilerinden** gelmesidir. Bu MVP'de
bu akışın temel iskeleti kuruldu:

- `backend/data_ingestion.py` — `.gml` veya `.zip` (tam shapefile seti:
  `.shp`+`.dbf`+`.shx`+`.prj`) dosyasını `geopandas`/`fiona` ile okur,
  WGS84'e (EPSG:4326) dönüştürür ve GeoJSON olarak döner.
- **Alan adı eşleştirme (alias mapping):** MAKS/İBB katmanlarının gerçek
  sütun adları henüz elimizde olmadığından, `ALIASES` sözlüğü olası
  sütun adlarını (büyük/küçük harf ve alt çizgiden bağımsız) hedef
  alanlara (`parcel_id`, `parcel_area_m2`, `floor_count`, `unit_count`,
  `population`, ...) eşler. **Gerçek MAKS şeması elinize geçtiğinde**
  yapılması gereken tek şey `ALIASES` içine gerçek sütun adlarını eklemek
  — eşleştirme/normalize mantığının kendisi değişmez.
- `POST /data/import` — dosya yükler, normalize edilmiş GeoJSON döner.
- `GET /data/sample` — gerçek MAKS dosyası gelene kadar arayüzü test
  etmek için 2 parsellik örnek (sahte) veri döner.
- **Frontend:** "0) MAKS / Kadastro Verisi" panelinden dosya yükleyin
  veya örnek veriyi açın; haritada beliren parsel/binalara tıklayıp
  "Seçileni Parsel/Bina Ayak İzi Olarak Ekle" ile doğrudan hesaplama
  akışına (parsel birleştirme dahil) dahil edebilirsiniz — manuel çizim
  akışıyla aynı veri yapısını kullanır, ikisi birlikte de kullanılabilir.

> Not: `geopandas`/`fiona` GDAL sistem kütüphanesine ihtiyaç duyar ve bu
> ajan sandbox'ında internet erişimi olmadığı için kurulup gerçek bir
> `.gml`/`.shp` dosyasıyla burada test edilemedi. Alan eşleştirme
> (`normalize_attributes`) mantığı geopandas'sız bağımsız olarak test
> edildi ve doğru çalışıyor; `load_vector_file`/`/data/import`'u gerçek
> bir İBB dosyasıyla kendi ortamınızda doğrulamanız gerekir.

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

1. ~~Gerçek kadastro/imar verisi entegrasyonu~~ → temel ingestion iskeleti
   eklendi (`/data/import`, `/data/sample`); gerçek MAKS GML/SHP
   dosyasıyla doğrulama ve `ALIASES` sözlüğünün gerçek şemaya göre
   güncellenmesi bekliyor.
2. Büyük dosyalar için performans (sunucu tarafında basitleştirme/
   tiling) ve doğrudan İBB açık veri servislerinden (WFS/WMS) otomatik
   çekim — dosya yüklemeye gerek kalmadan.
3. Birden fazla parsel/bina için optimizasyon (en uygun kat sayısı/kâr
   dengesi önerisi).
4. Gerçek generative AI tabanlı 3B bina/mimari model üretimi.
5. Deprem riski verisiyle ilişkilendirme (bu repodaki deprem
   dashboard'u ile entegrasyon — örn. risk skoruna göre dönüşüm önceliği).
6. Kullanıcı hesapları, proje kaydetme/paylaşma.
