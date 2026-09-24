# Otomasyon Geçiş Kılavuzu

Jenkins, JMeter ve RTTS işlerinizin TestRail yerine yeni sisteme sonuç
yazması için gereken değişiklikler.

Okuyucu: otomasyon işlerini yöneten test mühendisleri.

---

## Kısa cevap

İki satır değişiyor: **adres** ve **kimlik bilgisi**. Çağrıların şekli aynı.

```diff
- client = APIClient('https://dgpaysit.testrail.com/')
- client.user = 'otomasyon@dgpays.com'
- client.password = '<testrail api key>'
+ from testmgmt_client import TestManagement
+ client = TestManagement('http://test-yonetimi.dgpays.local:8080',
+                         token='tm_...')
```

Case id'leri korundu. `C15477` hâlâ aynı case — scriptlerinizdeki id'lere
dokunmanız gerekmiyor. Statü id'leri de aynı.

---

## 1. Token alın

Arayüzde **Yönetim → API Tokenları → Token üret**.

Token **bir kez** gösterilir. Jenkins'te credential olarak saklayın, koda
gömmeyin. İptal etmek tek tık; iptal edilen token anında 401 verir.

Token, üreten kullanıcının yetkileriyle çalışır. Otomasyon için ayrı bir
kullanıcı açıp **Tester** rolü vermek, insan hesabının token'ını kullanmaktan
daha iyidir: kim yazdı sorusunun cevabı net olur.

---

## 2. Çağrı karşılıkları

| TestRail | Yeni sistem | Not |
|---|---|---|
| `get_projects` | `get_projects()` | aynı |
| `get_suites/{p}` | `get_suites(p)` | ek olarak case/bölüm sayısı döner |
| `get_cases/{p}&suite_id=` | `get_cases(suite_id)` | sayfalı |
| `add_run/{p}` | `add_run(project_id, suite_id, name, ...)` | aynı alanlar |
| `add_results_for_cases/{r}` | `add_results_for_cases(run_id, results)` | **aynı gövde** |
| `add_result_for_case/{r}/{c}` | `add_result_for_case(run_id, case_id, status_id, **alanlar)` | aynı |
| `close_run/{r}` | `close_run(run_id)` | aynı |
| `get_tests/{r}` | `get_tests(run_id)` | aynı |

Statü id'leri değişmedi:

```
1 Passed   2 Blocked   3 Untested   4 Retouch   5 Failed
6 Aborted  7 Cancelled 8 Testing    9 NoRun    10 Deferred
```

---

## 3. Tipik gece koşumu

```python
from testmgmt_client import TestManagement, STATUS

tm = TestManagement(BASE_URL, token=TOKEN)

results = []
for case_id, outcome, duration in test_sonuclari:
    results.append({
        "case_id": case_id,
        "status_id": STATUS["passed"] if outcome else STATUS["failed"],
        "elapsed": f"{duration}s",
        "comment": hata_metni if not outcome else None,
        "defects": jira_no if not outcome else None,
    })

out = tm.run_from_results(
    project_id=19, suite_id=1696,
    name=f"RTTS Nightly {date.today()}",
    results=results,
)
print("Koşum:", out["url"], "| yazılan:", out["created"])
```

`run_from_results` üçünü birden yapar: koşum açar, sonuçları yazar, koşumu
kapatır.

---

## 4. Toplu yazmanın davranışı

`add_results_for_cases` **tek istekte binlerce sonuç** kabul eder. Test başına
bir istek atmayın: hem yavaştır hem de yarıda kesilirse koşum yarım kalır.

Koşumda olmayan bir case gönderilirse **atlanır, çağrı başarısız olmaz** ve
atlanan id'ler yanıtta döner:

```json
{"run_id": 73151, "created": 3, "unknown_case_ids": [999999999],
 "detail": "kosumda bulunmayan case'ler atlandi"}
```

Bu bilinçli: bir case suite'ten çıkarıldı diye 400 geçerli sonucun kaybolması
istenmez. Yanıttaki `unknown_case_ids` boş değilse script'iniz uyarı
yazdırsın — sessizce yutmayın.

---

## 5. Hata durumları

| Kod | Anlamı | Yapılacak |
|---|---|---|
| 401 `gecersiz token` | Token iptal edilmiş veya yanlış | Yeni token üretin |
| 401 `token suresi dolmus` | Süreli token'ın süresi bitmiş | Yeni token üretin |
| 403 `yetkiniz yok (write_results)` | Token sahibinin rolü yetersiz | Yönetim'den rol verin |
| 400 `tamamlanmis kosuma sonuc eklenemez` | Koşum kapatılmış | Yeni koşum açın |
| 404 `kosum bulunamadi` | run_id yanlış | — |

İstemci 502/503/504 hatalarında üstel geri çekilmeyle üç kez dener; sunucu
yeniden başlarken build'in düşmemesi için.

---

## 6. Geçiş sırasında paralel yazma

Geçiş haftasında iki sisteme birden yazmak isterseniz TestRail çağrısının
yanına ikinci bir blok ekleyin, **try/except içinde**:

```python
try:
    tm.add_results_for_cases(yeni_run_id, results)
except Exception as exc:
    logging.warning("yeni sisteme yazilamadi: %s", exc)
```

Yeni sistem henüz kritik değilken bir hatası TestRail'e yazmayı
engellememeli. Geçişten sonra sırayı ters çevirin.

---

## 7. Bağımlılık

`testmgmt_client.py` yalnızca Python standart kütüphanesini kullanır —
`requests` bile gerekmez. Build agent'a kopyalayın veya repoya ekleyin.

Denenmiş hali: koşum açma, 4 sonuç yazma (biri koşumda olmayan case),
koşum kapatma ve iptal edilmiş token'ın reddedilmesi bu istemciyle canlı
API'ye karşı doğrulandı.
