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

## 3DCityDB Pilot Kurulumu

Gerçek bina kütlesi (CityGML LoD2 ayak izi + ölçülmüş yükseklik/kat sayısı)
ve parsel verisini bir veritabanından sunmak için, dosya yükleme akışına
ek/alternatif olarak **3DCityDB (PostGIS şeması)** entegrasyonu eklendi.

> ⚠️ Bu bölümdeki Docker/SQL komutları, ajan sandbox'ında çalışan bir
> Docker daemon ve internet erişimi olmadığı için **burada
> çalıştırılıp test edilememiştir**. `backend/citydb.py` içindeki
> SQL sorguları 3DCityDB v4 şemasının dokümante edilen tablo yapısına
> (`building`, `thematic_surface`, `surface_geometry`, `cityobject`)
> göre yazıldı; pilot veriyle ilk denemede uyarlama gerekebilir (bkz.
> dosyanın başındaki not).

### 1) Veritabanını ayağa kaldırın

```
cd urban-transformation/docker
cp .env.example .env   # gerekirse şifreyi değiştirin
docker compose up -d
```

Bu, 3DCityDB v4 şemasını hazır şekilde içeren bir PostGIS konteyneri
başlatır (5432 portu). Güncel imaj/tag bilgisini çalıştırmadan önce
[Docker Hub](https://hub.docker.com/r/3dcitydb/3dcitydb-postgis)
üzerinden doğrulayın.

### 2) Pilot CityGML'i import edin

3DCityDB'nin resmi `citydb-tool` (veya klasik Importer/Exporter) CLI'ı ile:

```
citydb-tool import --db-host=localhost --db-port=5432 --db-name=citydb \
  --db-username=postgres --db-password=citydb pilot-bolge.gml
```

### 3) Parsel SHP'sini ayrı bir PostGIS tablosuna yükleyin

3DCityDB şeması bina/şehir nesnesi odaklıdır, kadastro parseli için ayrı
bir tablo kullanıyoruz; `ogr2ogr` ile WGS84'e (EPSG:4326) dönüştürerek
yükleyin (parsel SHP'nizin gerçek CRS'ini `-s_srs` ile belirtin, örn.
`EPSG:5253`):

```
ogr2ogr -f PostgreSQL "PG:host=localhost dbname=citydb user=postgres password=citydb" \
  parsel.shp -nln parcels.parcel -s_srs EPSG:5253 -t_srs EPSG:4326 -lco GEOMETRY_NAME=geom
```

### 4) Backend'i veritabanına bağlayın

`docker/.env.example`'daki değişkenleri backend'i başlatmadan önce
ortam değişkeni olarak ayarlayın (`CITYDB_HOST`, `CITYDB_PORT`,
`CITYDB_NAME`, `CITYDB_USER`, `CITYDB_PASSWORD`, `PARCELS_TABLE`).
Ayarlanmazsa `/citydb/*` endpoint'leri `501` döner, dosya yükleme
(`/data/import`) akışı bundan etkilenmeden çalışmaya devam eder.

### 5) Kullanım

- `GET /citydb/buildings?minx&miny&maxx&maxy` — bbox içindeki gerçek
  bina ayak izi + yükseklik/kat sayısını GeoJSON olarak döner. Frontend'de
  "Görünen Alanı 3DCityDB'den Yükle" butonu, haritanın görünen sınırlarını
  (`map.getBounds()`) kullanarak bu endpoint'i çağırır ve binaları gerçek
  yüksekliğiyle 3B ekstrüde eder (artık parametrik tahmin değil).
- `POST /citydb/context` — çizilen/seçilen bir parsel geometrisiyle
  kesişen binaları bulup toplam ayak izi alanı ve maksimum kat sayısını
  döner; "Seçili Parselin Mevcut Durumunu Çek" butonu bunu çağırıp
  "Mevcut Durum" formunu otomatik doldurur (manuel bina ayak izi çizmeye
  gerek kalmadan).
- `GET /citydb/parcels?minx&miny&maxx&maxy` — `PARCELS_TABLE`'daki
  parselleri, `data_ingestion.py`'daki aynı alias-eşleştirme mantığıyla
  normalize edip döner.

## Pazar Konumlandırması

Türkiye'de bu alanda zaten ticarileşmiş rakipler var: **Evveko**
(mülk sahibini denetimden geçmiş müteahhitle eşleştiren, müteahhitten
abonelik + proje bazlı %3-5 komisyon alan bir **reaktif** platform) ve
**Kolayimar** (81 ilde TKGM/e-Plan canlı entegrasyonlu, ücretsiz **tek
parsel** sorgu/yatırım analizi aracı). Bu, sektörde gerçek bir ödeme
isteği olduğunu doğruluyor, ama her ikisi de "kullanıcı başvurana kadar
bekleyen" ya da "bir parseli tek tek sorgulayan" araçlar.

Bu proje, bu boşluğa odaklanır: **proaktif, şehir ölçekli Kârlılık
Endeksi taraması** (`backend/scan.py`, `/scan` endpoint'i,
"6) Kârlılık Taraması" frontend paneli) — müteahhidin başvuru beklemeden
yüklü tüm parselleri otomatik tarayıp en kârlı olanları sıralaması — ve
bunu besleyen gerçek 3D bina hacmi (3DCityDB) + bölgesel fiyat tahmin
modeli (`backend/price_model.py`). Global tarafta Archistar/TestFit/
Giraffe gibi olgun "AI feasibility + site selection" araçları var, ama
Türk imar/kadastro mevzuatına ve kentsel dönüşümün "mevcut hak
sahipliği + şerefiye paylaşımı" problemine değinen hiçbiri yok.

## Bölgesel Fiyat Tahmini ve Kârlılık Taraması

- `backend/price_model.py` — "GWR-lite": gerçek çok değişkenli GWR
  (`mgwr` + gerçek satış verisi) yerine, dış bağımlılık gerektirmeyen,
  coğrafi mesafeye göre Gauss çekirdek ağırlıklı yerel ortalama
  (Nadaraya–Watson tipi kernel regresyon) ile bölgesel m² satış fiyatı
  tahmini yapar. `synthetic_sales()` ürettiği veri **tamamen SENTETİKTİR**
  — sadece demo/test amaçlıdır, gerçek değerleme için kullanılamaz.
  Gerçek satış verisi/`mgwr` temin edilince bu modülün dış API'si
  (`predict()` girdi/çıktısı) aynı kalarak çok değişkenli GWR'a
  yükseltilebilir.
- `backend/scan.py` — `calculations.calculate()`'i, fiyat tahminini her
  parsel için tekrar tekrar çalıştırarak bir parsel listesini Kârlılık
  Endeksi'ne (tahmini kâr / tahmini süre) göre sıralar.
- `POST /price/sample-sales`, `POST /price/predict`, `POST /scan` —
  ilgili backend endpoint'leri.
- **Frontend:** "6) Kârlılık Taraması" paneli, "0) MAKS / Kadastro
  Verisi" ile yüklenmiş parselleri tarar, sonuçları haritada Kârlılık
  Endeksi'ne göre kırmızı→sarı→yeşil renklenen bir dolgu katmanı
  (`scan-results-fill`) olarak gösterir ve sıralı listeyi yan panelde
  listeler.

> ⚠️ Sandbox'ta `fastapi`/`pydantic` kurulu olmadığından `/scan` ve
> `/price/*` endpoint'leri canlı bir HTTP isteğiyle test edilememiştir;
> `scan.py`'ın iç mantığı `pydantic`'i geçici olarak stub'layan bağımsız
> bir Python betiğiyle uçtan uca doğrulandı (parsel → fiyat tahmini →
> TAKS/KAKS hesabı → Kârlılık Endeksi sıralaması doğru çalışıyor).
> Frontend tarafı (`btn-scan` mantığı) `node --check` ile sözdizimi
> olarak doğrulandı, gerçek bir tarayıcıda backend'e bağlı şekilde
> test edilmedi.

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

Projenin nihai vizyonu, paydaşlar (müteahhit, mühendis, mimar, emlakçı,
vatandaş/site yönetimi) arasındaki fizibilite ve mutabakat sürecini
ulusal ölçekte otomatikleştiren bir platformdur — tam şartname için
[`docs/VISION.md`](docs/VISION.md). Bu kod tabanı şu anda bu vizyonun
küçük bir alt kümesini gerçekleştiriyor; aşağıdaki fazlama, vizyondaki
maddelerin **gerçekçi inşa edilebilirliğine** göre yapılmıştır.

### Faz 0 — Tamamlanan MVP
- TAKS/KAKS, kat sayısı, bağımsız bölüm, hak sahibi/müteahhit payı,
  maliyet/kâr hesaplama motoru (`/calculate`).
- MapLibre tabanlı 3B harita: parsel/bina ayak izi çizme, parsel
  birleştirme, önerilen binanın parametrik 3B kütle gösterimi.
- MAKS/İBB GML/SHP içe aktarma iskeleti (`/data/import`, alias eşleme).
- 3DCityDB/PostGIS pilot entegrasyonu (`/citydb/buildings`,
  `/citydb/context`, `/citydb/parcels`) — pilot veriyle doğrulanmayı
  bekliyor.
- **Proaktif Kârlılık Endeksi taraması + GWR-lite fiyat tahmini**
  (`/scan`, `/price/predict`, "6) Kârlılık Taraması" paneli) — bkz.
  "Bölgesel Fiyat Tahmini ve Kârlılık Taraması" bölümü yukarıda; bu,
  pazardaki reaktif/tek-parsel rakiplerden (Evveko, Kolayimar) ayrışan
  ana farklılaştırıcı özelliktir.

### Faz 1 — Mevcut altyapı üzerine doğrudan inşa edilebilir
Bunlar, ek dış API/kurumsal erişim gerektirmeden, mevcut hesaplama
motoru ve 3DCityDB pilotu üzerine kodlanabilir:
1. ~~"En Kârlı Bölge" tarama + ısı haritası~~ — **yapıldı** (`/scan`,
   bkz. yukarıda). Sıradaki adım: sentetik fiyat verisini gerçek/açık
   satış verisiyle değiştirmek ve heatmap'i tek tek poligon yerine
   gerçek bir MapLibre heatmap katmanına (büyük parsel sayılarında
   performans için) taşımak.
2. **Viewshed / Sky View Factor 3D analizi** (vizyon §1.C): gerçek ışın
   atma (ray casting) gerektirir; MapLibre'de yapılamaz, CesiumJS/3D
   Tiles tabanlı bir "Mühendislik ve Analiz Katmanı" (vizyon §5) eklenmesi
   gerekir — 3DCityDB binalarıyla beslenebilir.
3. ~~GWR (coğrafi ağırlıklı regresyon) fiyat tahmin iskeleti~~ —
   **GWR-lite olarak yapıldı** (`price_model.py`). Sıradaki adım: gerçek
   satış verisi + `numpy`/`mgwr` temin edilince çok değişkenli (m², kat,
   manzara, deprem riski) gerçek GWR'a yükseltmek.
4. Gerçek LoD2 bina mesh'inin (sadece ayak izi değil, çatı/cephe) 3D
   Tiles/glTF olarak CesiumJS veya deck.gl Tile3DLayer ile gösterilmesi
   (MapLibre'nin yerini/ekini alarak).
5. Deprem riski verisiyle ilişkilendirme — bu repodaki deprem
   dashboard'u ile entegrasyon (örn. risk skoruna göre dönüşüm önceliği).
6. Kullanıcı hesapları, proje kaydetme/paylaşma.

### Faz 2 — Dış kurumsal veri/erişim gerektirir (şu an sadece tasarım)
Bunlar gerçek kod yazılarak "şimdi" çözülemez; ilgili kurumla veri
erişimi/API anlaşması olmadan iskelet ötesine geçilemez:
- **TAKBİS/LADM (ISO 19152) 3D kadastro modellemesi** (vizyon §1.A) —
  TAKBİS verisine resmi erişim gerekir.
- **HKMO/İMO canlı birim maliyet API'si ve TMMOB "dijital kaşe"
  sertifikasyonu** (vizyon §4.A) — meslek odalarıyla kurumsal entegrasyon
  ve yetkilendirme gerekir.
- **e-Devlet tabanlı Dijital Uzlaşma Portalı** (vizyon §4.C) — e-Devlet
  kapısı entegrasyonu resmi yetki/protokol gerektirir.
- **BIM/IFC ve LiDAR nokta bulutu entegrasyonu (Virtual Singapore
  benzeri dijital ikiz)** (vizyon §1, §5) — pilot bölge için bu veri
  setlerinin temin edilmesi gerekir.

### Faz 3 — İş/hukuk modeli (yazılım görevi değil)
Vizyon §6'daki SaaS aboneliği, rapor başına ücretlendirme ve komisyon
modeli; ürün/iş geliştirme ve hukuki danışmanlık gerektiren ticari
kararlardır — bu README'nin veya kod tabanının kapsamı dışındadır,
ancak ürün olgunlaştığında bir faturalama/yetkilendirme katmanı
(örn. Stripe + rol bazlı erişim) olarak teknik karşılığı eklenebilir.
