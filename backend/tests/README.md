Yazılı: uygulamayı devralacak geliştiriciler için.

# Backend testleri

43 test; API'yi FastAPI'nin `TestClient`'ı ile uçtan uca çalıştırır, mock
kullanmaz. Bulduğu ilk üç hata, neden var olduklarını iyi özetliyor:

- Temiz bir kurulumda `statuses` tablosu boştu; ilk koşum oluşturma foreign
  key hatasıyla patlıyordu. Bizim veritabanımızda durumlar TestRail
  göçünden geldiği için kimse fark etmemişti.
- Aynı dosyayı iki farklı case'e eklemek 500 veriyordu: ek kimliği yalnızca
  içerikten türetiliyordu ve benzersizdi.
- `Read-only` rolündeki bir kullanıcı suite, bölüm ve plan oluşturabiliyor,
  koşum adını değiştirebiliyordu — bu uç noktalarda yetki kontrolü hiç yoktu.

## Çalıştırma

Testler şemayı silip yeniden kurar, bu yüzden **kendi veritabanında** çalışır
(`testmgmt_test`). Gerçek veritabanının adını gösterirseniz conftest hata
verip durur.

Veritabanını bir kez oluşturun (uygulama rolünde `CREATEDB` yetkisi yok, bu
bilinçli):

```bash
python ops/mktestdb.py        # postgres süper kullanıcısıyla, bir kez
```

Sonra:

```bash
cd backend
python -m pytest              # .env.test dosyasını kendisi bulur
```

Farklı bir veritabanı için:

```bash
TEST_DATABASE_URL=postgresql+psycopg://tm:...@host:5432/testmgmt_ci python -m pytest
```

## Kapsam

| Dosya | Ne doğruluyor |
|---|---|
| `test_auth.py` | giriş, API tokenları, rol ve proje bazlı yetkiler |
| `test_cases.py` | özel alan birleştirme, adım yazımı, geçmiş, soft delete |
| `test_structure.py` | bölüm ağacı, taşıma, döngü koruması, silme kuralları |
| `test_execution.py` | koşum/test/sonuç akışı, adım sonuçları, silme sonrası durum |
| `test_import.py` | CSV eşleştirme, çok satırlı adımlar, kuru çalışma |
| `test_attachments.py` | yükleme, tekilleştirme, sonuca bağlama, silme |

Yeni bir uç nokta eklerken: yetki kontrolünü test edin. Yukarıdaki üçüncü
madde, o testin olmamasının maliyetiydi.
