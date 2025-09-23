# Earthquake Analytics Dashboard

Bilimsel ve hobi amaçlı herkes için, USGS ve AFAD kaynaklı güncel ve geçmiş depremleri harita üzerinde, şehir seçerek ve zamana göre interaktif olarak analiz edebileceğiniz web uygulaması.

## Özellikler
- Global ve Türkiye depremleri (AFAD & USGS)
- Harita üzerinde şehir/bölge seçimi
- Zamana göre slider (en eski > en yeni)
- Büyüklük filtresi
- Kaynak karşılaştırması
- Anlık veri çekme (cache yok)
- PowerBI gibi BI araçları için JSON API (hazır)
- Tamamen açık kaynak & Python tabanlı

## Kurulum
1. Gerekli kütüphaneleri kurun:
    pip install -r requirements.txt

2. Backend API (FastAPI) başlat:
    cd backend
    uvicorn main:app --reload
    # API http://localhost:8000 adresinde çalışacak

3. Dashboard (Dash) başlat:
    cd ../dashboard
    python app.py
    # Dashboard http://localhost:8050 adresinde çalışacak

## Geliştirme ve Özelleştirme
- Dilerseniz yeni kaynaklar ekleyin (örn. EMSC).
- Arayüze yeni filtreler, harita stilleri veya animasyonlar ekleyin.
- PowerBI veya diğer BI araçlarına veri sunmak için backend'i kullanabilirsiniz.

MIT Lisansı ile açık kaynak.  
Katkıda bulunmak için pull request gönderebilirsiniz!