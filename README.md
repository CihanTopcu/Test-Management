# DGPays Test Yönetimi

TestRail yerine geçen, şirket içinde barındırılan test yönetim uygulaması.
Beş yıllık TestRail verisi bu uygulamaya taşındı ve çalışma buradan devam
ediyor.

## Şu an taşınmış veri

| | |
|---|---|
| Proje | 16 |
| Test case | 65.227 (64.212 aktif + 1.015 silinmiş) |
| Case adımı | 147.503 |
| Bölüm / suite | 9.278 / 204 |
| Milestone | 558 |
| Koşum | 13.929 (1.535 aktif + 12.394 arşiv) |
| Test | 1.064.011 |
| Sonuç | 1.090.895 |
| Case geçmişi | 152.872 |
| Ek dosya | 491 (115 MB) |

`migration/verify.py` dökümle veritabanını karşılaştırır ve birebir örtüştüğünü
doğrular; `migration/audit.py` veri kalitesini denetler (referans bütünlüğü,
özel alan geçerliliği, karakter kodlaması, ek sağlama toplamları).

## Yapı

```
backend/     FastAPI + SQLAlchemy 2.0 + PostgreSQL 17   (app/, tests/)
frontend/    React 19 + TypeScript + Vite               (src/)
migration/   TestRail'den dökme, yükleme, doğrulama, denetim, fark alma
clients/     Otomasyon için Python istemcisi
ops/         Yedekleme, geri yükleme, test veritabanı kurulumu
```

Ayrıntılar: kurulum ve işletim için [DEPLOY.md](DEPLOY.md), TestRail'den
geçiş planı için [CUTOVER.md](CUTOVER.md), test paketi için
[backend/tests/README.md](backend/tests/README.md).

## Geliştirme ortamı

```bash
cp .env.example .env          # en az DB_PASSWORD ve SECRET_KEY'i değiştirin

# arka uç
pip install -r backend/requirements.txt
PYTHONPATH=backend python -m uvicorn app.main:app --port 8010

# ön yüz
cd frontend && npm install && npm run dev
```

Boş bir veritabanında uygulama şemayı kendi kurar, varsayılan durum/tip/
öncelik/şablon listelerini oluşturur ve `.env` içindeki bilgilerle bir
yönetici hesabı açar.

## Testler

```bash
python ops/mktestdb.py        # bir kez, postgres süper kullanıcısıyla
cd backend && python -m pytest
```

56 test; API'yi uçtan uca çalıştırır, mock kullanmaz. Testler şemayı silip
yeniden kurduğu için yalnızca kendi veritabanında çalışır ve gerçek
veritabanının adını görürse durur.

## Notlar

- Arayüz ve hata mesajları Türkçedir.
- Veri (`data/`), yedekler (`backups/`) ve `.env` depoya dâhil değildir.
- TestRail'den taşınan kayıtlar, o günkü hâliyle korunur: silinmiş case'ler
  `is_deleted` ile, arşivlenmiş koşumlar `is_archived` ile saklanır ve
  arşivlenmiş koşumlar salt okunurdur.
