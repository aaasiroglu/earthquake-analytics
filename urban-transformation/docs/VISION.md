# 3D GIS ve Yapay Zekâ Destekli Kentsel Dönüşüm Karar Destek Sistemi (KDS)
## Teknik Şartname ve Sistem Mimarisi Dökümanı

> Bu döküman, projenin **nihai/ulusal ölçek vizyonunu** tanımlar. Şu anki
> kod tabanı (`urban-transformation/`), bu vizyonun küçük bir alt kümesini
> (TAKS/KAKS hesaplama + 3B görselleştirme MVP'si ve bir 3DCityDB pilot
> entegrasyonu) gerçekleştirir. Hangi maddenin hangi aşamada ele
> alınacağı için ana `README.md`'deki "Yol Haritası" bölümüne bakın.

Bu döküman; kentsel dönüşüm ve afet odaklı kent planlamasında Müteahhit, Mühendis, Mimar, Emlakçı ve Vatandaş (Site Yönetimi) arasındaki finansal fizibilite ve sosyal mutabakat süreçlerini tamamen bilimsel, nesnel ve otomatik hale getiren ulusal ölçekli platformun mimarisini tanımlar.

---

## 1. Akademik ve Bilimsel Altyapı (Global Standartlar)

Sistemin üreteceği kararların ve değerleme raporlarının hukuki, mali ve akademik olarak "Sektör Standardı ve Referansı" kabul edilmesi için aşağıdaki uluslararası literatür modelleri uygulanmıştır:

### A. LADM (Land Administration Domain Model - ISO 19152)
* **Uygulama:** Mülkiyet, hukuk ve mekansal veriyi birleştiren küresel ISO standardıdır. Türkiye'deki TAKBİS (Tapu ve Kadastro Bilgi Sistemi) verileri bu ontolojiye eşlenerek, mülkiyet hakları 3 boyutlu (**3D Kadastro**) olarak modellenir.

### B. Geographically Weighted Regression (GWR) & Spatial Econometrics
* **Uygulama:** Klasik doğrusal tahmin modelleri yerine, Tobler'in Birinci Coğrafya Kanunu ("Birbirine yakın nesneler, uzak nesnelere göre daha ilişkilidir") baz alınarak **Coğrafi Ağırlıklı Regresyon** algoritması kullanılır. Yapay zekâ hiper-parametreleri coğrafi koordinatlara göre dinamik olarak optimize edilerek piyasa tahminlerindeki hata payı (MAPE) %3'ün altına indirilir.

### C. 3D Mikro-Mekansal Şerefiye Analizi (Vertical Hedonic Pricing)
Uluslararası CAMA (Computer-Assisted Mass Appraisal) standartlarına uygun olarak, her bir bağımsız bölümün değeri 3D GIS katmanında şu algoritmalarla nesnelleştirilir:
* **Viewshed (Görüş Alanı) İndeksi:** Daire pencerelerinden fırlatılan 3D ışınlar (ViewCone) ile deniz, yeşil alan veya şehir silüeti görme oranının matematiksel hesabı.
* **Sky View Factor (SVF):** Çevre yapılardan kaynaklı gün ışığı alma ve gölgelenme sürelerinin simülasyonu.
* **Dikey Kat Etkisi:** Kat yüksekliği arttıkça değişen gürültü, hava kalitesi ve manzara priminin algoritmik ağırlıklandırılması.

---

## 2. Global Örnekler ve Entegre Edilen Pozitif Maddeler (Benchmarks)

| Global Örnek | Odak Noktası | Platforma Entegre Edilen Pozitif Madde |
| :--- | :--- | :--- |
| **Zillow (Zestimate) & GeoPhy (ABD)** | Yapay Zekâ Tabanlı Otomatik Değerleme (AVM) | Hiper-yerel ve zamana bağlı (4D) gayrimenkul fiyat öngörü boru hatları (data pipelines). |
| **Kadaster (Hollanda)** | 3B Kadastro ve Bilimsel Kitlesel Değerleme | Kamusal güven için meslek odaları onaylı "Açık Değerleme Metodolojisi". |
| **Virtual Singapore (Singapur)** | Şehrin Kompleks Dijital İkizi (Digital Twin) | BIM (IFC) modellerinin doğrudan haritaya yüklenerek inşaat öncesi mikroklima ve afet simülasyonlarının yapılması. |

---

## 3. Müteahhit İçin "En Kârlı Bölge" Optimizasyon Algoritması

Sistem, şehir genelindeki tüm yapıların kat ve bağımsız bölüm sayılarını tarayarak en yüksek finansal dönüşüm potansiyeline sahip parselleri otomatik olarak listeler ve akıllı alarmlar üretir.

### Kârlılık Endeksi Formülü

$$K = \frac{(V_{yeni} \times P_{satış}) - (V_{mevcut} \times P_{şerefiye}) - C_{inşaat} - C_{lojistik}}{Zaman}$$

* **$V_{yeni}$ (Yeni İnşaat Hacmi):** İmar planı açık verilerinden (TAKS/KAKS, emsal artışları) gelen maksimum 3D bina zarfı.
* **$V_{mevcut}$ (Mevcut Hacim):** Mevcut kat ve bağımsız bölüm sayısı (Vatandaşa verilmesi zorunlu minimum hak sahipliği).
* **$P_{satış}$:** Yapay zekanın (GWR) projenin tamamlanacağı yıl için öngördüğü bölge rayiç satış fiyatı.
* **$C_{inşaat}$:** Meslek odalarından (İMO) anlık çekilen yapı sınıfı maliyet endeksi ve 3D zemin analizinden gelen altyapı/temel maliyetleri.

---

## 4. Paydaş Bazlı Karar Destek Sistemi (DSS) ve Rollerin Entegrasyonu

Platform, tüm paydaşların (Meslek Odaları, Kooperatifler, Devlet ve Özel Sektör) üzerinde uzlaştığı objektif kuralları birer yazılım kısıtı olarak işler.

### A. Meslek Odaları ve Kooperatifler (Veri & Onay Makamı)
* **Entegrasyon:** Harita Mühendisleri Odası (HKMO) ve İnşaat Mühendisleri Odası (İMO) birim maliyet ve parselasyon kriterleri API ile sisteme canlı bağlanır.
* **Standartlaşma:** Üretilen her resmi fizibilite ve paylaşım raporunun altına *"TMMOB X Odası standartlarına uygun olarak hesaplanmıştır"* dijital kaşesi basılır.

### B. Müteahhitler İçin (B2B SaaS)
* **Akıllı Alarm:** Haritada kat sayısı düşük, bağımsız bölüm sayısı az ancak imar planında emsal artışı almış, yapay zekâ kârlılık oranı yüksek parseller "Yatırıma Hazır Adalar" olarak ısı haritasında (Heatmap) parlar.
* **Zemin & Altyapı Risk Analizi:** 3D GIS zemin katmanı sayesinde, kazı başlamadan önce sismik risk, sıvılaşma durumu ve altyapı çakışma (Clash Detection) analizleri müteahhidin ekranına uyarı olarak düşer.

### C. Vatandaş ve Site Yöneticileri İçin (Sosyal Mutabakat)
* **Dijital Uzlaşma Portalı:** Kat malikleri e-Devlet tabanlı güvenli arayüz ile projeye onay verdikçe bina rengi haritada canlı olarak değişir (%67 yasal sınıra ulaşan binalar yeşile döner).
* **Adil Paylaşım:** Müteahhit ile vatandaş arasındaki mülkiyet tartışmaları, sistemin ürettiği nesnel 3D şerefiye puanı ile çözülür.

### D. Emlakçılar ve Mühendisler İçin
* **Dönüşüm Brokerlığı:** Emlakçılar sisteme girdikleri yaşlı konut ilanlarına sistem tarafından otomatik üretilen *"Bu mülk kentsel dönüşüme girdiğinde değerini %140 artırma potansiyeline sahiptir"* bilimsel etiketini ekler. Yıkım sürecinde evini tahliye edecek ailelerin geçici kiralık konut eşleştirmeleri sistem tarafından emlakçılara lojistik iş emri olarak atanır.

---

## 5. Teknolojik Mimari ve Açık Veri (Open Data) Hibrit Yapısı

Sistem, yüksek lisans maliyetlerinden bağımsız, sürdürülebilir ve yüksek performanslı bir açık kaynak kod (Open-Source) mimarisi üzerine kurulmuştur:

* **Arayüz ve Keşif Katmanı (MapLibre GL JS):** Milyonlarca parselin imar durumunu, vector tile teknolojisi ile mobil cihazlarda bile hafif, hızlı ve akıcı bir şekilde 2D/2.5D olarak görselleştirir.
* **Mühendislik ve Analiz Katmanı (CesiumJS & 3D Tiles):** Seçilen pilot bölgelerde BIM/IFC modellerini, LiDAR nokta bulutlarını, 3D şerefiye ışın simülasyonlarını ve yeraltı katmanlarını tam teşekküllü 3D GIS gücüyle çalıştırır.
* **Veri Standartları:** Coğrafi ve semantik verilerin taşınmasında **CityJSON** ve **3D Tiles** açık standartları kullanılır.
* **Siber Güvenlik ve KVKK Duvarı:** Bina geometrisi ve imar durumu gibi kamusal veriler **Açık Katman (Open Data)** olarak herkesle paylaşılırken; mülkiyet ve kişisel sözleşme verileri e-Devlet kapısı arkasındaki izole **Güvenli Katman (Secure Layer)** içinde maskelenerek korunur.

---

## 6. Yüksek Kârlı Ticari Gelir Modeli (SaaS & PropTech)

1.  **Kurumsal B2B SaaS Aboneliği:** İnşaat firmaları ve müteahhitlerin "kârlılık alarmı veren parselleri ve 3D imar kısıtlarını sorgulaması" için aylık/yıllık kurumsal lisanslama.
2.  **Rapor Başına Ödeme (Pay-per-Report):** Kat maliklerinin, site yönetimlerinin ve emlakçıların noter sözleşmelerinde veya mahkemelerde yasal dayanak olarak kullanabileceği **"Yapay Zekâ Onaylı 3D Şerefiye ve Adil Paylaşım Raporu"** sertifikalandırma ücreti.
3.  **Danışmanlık ve Entegrasyon Komisyonları:** Sistem üzerinde uzlaşması tamamlanan ve ihalesi yapılan projelerden, ayrıca sisteme akredite olan kentsel dönüşüm emlak ofislerinden alınan platform işlem payı.
