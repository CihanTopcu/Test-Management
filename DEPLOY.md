# Kurulum ve İşletim

DGPays Test Yönetimi'ni şirket içi bir sunucuya kurmak, yedeklemek ve
güncellemek için gereken her şey. Tek gereksinim: Docker ve Docker Compose
kurulu bir Linux sunucu.

---

## 1. İlk kurulum

```bash
git clone <repo> /opt/test-yonetimi
cd /opt/test-yonetimi

cp .env.example .env
```

`.env` içinde **en az iki satırı** değiştirin:

```bash
DB_PASSWORD=<güçlü bir parola>
SECRET_KEY=<rastgele 64 karakter>
```

`SECRET_KEY` oturum jetonlarını imzalar. Değiştirilirse herkesin oturumu
kapanır; paylaşılmamalı ve yedeklenmelidir.

```bash
openssl rand -base64 48        # SECRET_KEY üretmek için
```

Ardından:

```bash
docker compose up -d --build
docker compose logs -f api     # ilk açılışta yönetici parolası buraya yazılır
```

İlk açılışta uygulama boş veritabanını görür, şemayı ve varsayılan rolleri
oluşturur, bir yönetici hesabı açar. `BOOTSTRAP_PASSWORD` boş bırakıldıysa
**geçici parola container log'una bir kez yazılır** — not alıp ilk girişten
sonra değiştirin.

Arayüz: `http://<sunucu>:8080` (portu `WEB_PORT` ile değiştirebilirsiniz).

### Ağ yüzeyi

Yalnızca web portu dışarı açılır. PostgreSQL ve API iç ağda kalır — bir test
yönetim sisteminin veritabanının ofis ağından erişilebilir olması için bir
sebep yok.

---

## 2. TestRail verisini yükleme

Göç araçları uygulamanın dışında, `migration/` altında çalışır ve
doğrudan veritabanına bağlanır.

```bash
# .env içine TestRail erişim bilgilerini ekleyin
TESTRAIL_URL=https://dgpaysit.testrail.com
TESTRAIL_USER=<e-posta>
TESTRAIL_KEY=<API anahtarı>

python migration/dump.py all          # TestRail'i diske indirir
python migration/fetch_blobs.py       # ek dosyalarının ikili içeriği
python migration/load.py all          # diskten veritabanına
python migration/verify.py            # sayım ve alan karşılaştırması
python migration/audit.py             # veri kalitesi denetimi
```

`dump.py` ve `load.py` **yeniden başlatılabilir**: yarıda kalırsa kaldığı
yerden devam eder, iki kez çalıştırmak kayıt çoğaltmaz.

`verify.py` bir fark bulursa çıkış kodu 1 verir — geçiş kararını buna
bağlayabilirsiniz.

---

## 3. Yedekleme

```bash
./ops/backup.sh                  # ./backups altına
KEEP_DAYS=90 ./ops/backup.sh     # saklama süresini değiştirerek
```

Her çalıştırma iki dosya üretir: veritabanı dökümü ve ek dosyalarının arşivi.

**İkisi de gerekli.** Veritabanı, TestRail aboneliği sürdüğü sürece yeniden
üretilebilir; **ek dosyaları üretilemez** — TestRail kapandıktan sonra o
görsellerin başka bir kopyası kalmaz.

Gecelik yedek için crontab:

```
30 2 * * * cd /opt/test-yonetimi && ./ops/backup.sh >> /var/log/tm-backup.log 2>&1
```

Yedeği düzenli olarak **geri yükleyerek** sınayın; sınanmamış yedek yedek
değildir.

### Geri yükleme

```bash
./ops/restore.sh backups/db-20260924-023000.dump \
                 backups/attachments-20260924-023000.tar.gz
```

Mevcut veritabanını siler, onay ister.

---

## 4. Güncelleme

```bash
cd /opt/test-yonetimi
git pull
docker compose up -d --build
```

Şema değişiklikleri açılışta uygulanır. **Güncellemeden önce yedek alın.**

---

## 5. E-posta bildirimleri

`.env` içinde `SMTP_HOST` boşken uygulama sorunsuz çalışır: bildirimler
yalnızca uygulama içi listeye düşer. SMTP tanımlandığında:

```bash
SMTP_HOST=smtp.dgpays.local
SMTP_PORT=587
SMTP_USER=test-yonetimi
SMTP_PASSWORD=<parola>
SMTP_FROM=test-yonetimi@dgpays.com
PUBLIC_URL=http://test-yonetimi.dgpays.local:8080
```

`PUBLIC_URL` e-postadaki bağlantıların kurulduğu adrestir; yanlışsa
bildirimler gider ama linkler çalışmaz.

Kuyruğu boşaltmak (bir zamanlanmış görev çağırmalı):

```bash
curl -X POST http://localhost:8080/api/notifications/flush \
     -H "Authorization: Bearer <yönetici token>"
```

---

## 6. Otomasyon erişimi

CI işleri tarayıcı oturumu kullanamaz. Yönetim → API Tokenları'ndan bir token
üretin ve sonuçları toplu olarak yazın:

```bash
curl -X POST http://<sunucu>:8080/api/runs/<run_id>/results \
  -H "Authorization: Bearer tm_..." \
  -H "Content-Type: application/json" \
  -d '{"results":[{"case_id":15477,"status_id":1,"elapsed":"12s"}]}'
```

Çağrı TestRail'in `add_results_for_cases` ucuyla aynı şekli kullanır;
mevcut işlerinizde adres ve kimlik bilgisi dışında değişiklik gerekmez.

---

## 7. Sorun giderme

| Belirti | Bakılacak yer |
|---|---|
| Sayfa açılmıyor | `docker compose ps` — `web` ve `api` sağlıklı mı |
| Giriş yapılamıyor | `docker compose logs api` — ilk açılış parolası burada |
| "yetkiniz yok" | Yönetim → Kullanıcılar ve Roller — kullanıcının rolü |
| Görseller kırık | Ek volume'u bağlı mı: `docker volume ls` |
| API yavaş | `docker compose exec db psql -U tm -d testmgmt -c "\di"` — indeksler |

Servis günlükleri:

```bash
docker compose logs -f api
docker compose logs -f db
```

---

## 8. Testler

Uygulamanın kendi test paketi `backend/tests` altında; API'yi uçtan uca
çalıştırır, mock kullanmaz. Kendi veritabanında koşar ve şemayı silip
yeniden kurar — gerçek veritabanının adını görürse durur.

```bash
python ops/mktestdb.py     # bir kez, postgres süper kullanıcısıyla
cd backend && python -m pytest
```

Ayrıntılar ve testlerin bulduğu ilk hatalar: `backend/tests/README.md`.

## 9. Zamanlanmış raporlar

Kullanıcılar kendi ayar ekranından (sağ üstte adlarına tıklayarak) rapor
aboneliği açar: gece kırılan testler, proje özeti, yaklaşan milestone'lar.
Teslimatı uygulama kendi başına yapmaz; e-posta kuyruğunu boşaltan aynı
zamanlayıcı bu ucu da çağırmalı:

```
*/15 * * * *  curl -s -X POST -H "Authorization: Bearer <admin tokeni>"               http://localhost:8080/api/report-subscriptions/dispatch
```

On beş dakikada bir çağırmak güvenli: her abonelik günde en fazla bir kez
gönderilir. Sık çağırmanın faydası, seçilen saatte konteyner kapalıysa günü
atlamak yerine açılır açılmaz göndermesidir.

İçinde bildirilecek bir şey olmayan rapor gönderilmez — pencere yine ilerler,
yani bir sonraki rapor kimseye söylenmemiş bir dönemi tekrar taramaz.

### Kim ne üretti

Tüm Projeler sayfasının altındaki tablo, hangi hesabın ne kadar sonuç
girdiğini, case yazdığını ve düzenlediğini alan alan gösterir. Taşınan
veride hesapların çoğu paylaşımlı takım girişidir, bu yüzden tablo kişiyi
değil **alanı** ölçer; bir hesabın robot mu insan mı olduğunu ayıran tek
işaret **yazım payı**dır.

Eşitleme, değişen case'lerin düzenleme geçmişini de çeker
(`get_history_for_case`); bu olmadan case yeni değerleriyle gelir ama kimin
değiştirdiği kaybolur.

## 10. İstek sınırı

Giriş denemeleri (dakikada 10) ve otomasyon yazmaları (dakikada 600 sonuç)
sınırlıdır. Sayaç bellekte, süreç başına tutulur; bu kurulum tek API
konteyneri çalıştırdığı için tablo bütünüyle budur. Birden fazla işçiyle
çalıştırırsanız her biri kendi penceresini tutar ve etkin sınır çarpılır.

`RATE_LIMIT_ENABLED=false` yalnızca test koşarken anlamlıdır.

## 11. Henüz yapılmamış olanlar

Dürüst olmak gerekirse bu kurulum üretime ilk adım; şunlar eksik:

- **HTTPS yok.** Önüne bir ters vekil (nginx/Traefik) koyup sertifika
  bağlanmalı. Parolalar ve tokenlar şu an şifrelenmemiş bağlantıdan geçer.
- **Şema göçü Alembic ile yönetilmiyor.** Tablolar açılışta oluşturuluyor;
  ileride sütun değiştiren bir güncelleme için Alembic devreye alınmalı.
- **Docker imajları bu ortamda derlenip sınanmadı** (geliştirme makinesinde
  Docker kurulu değil). Bağımlılıkların eksiksiz olduğu doğrulandı ama ilk
  `docker compose up --build` çıktısını izleyin.
- **İzleme/uyarı yok.** Sağlık ucu var (`/api/health`), bir izleme sistemine
  bağlanmalı.
- **İstek sınırı tek süreç varsayar.** Birden fazla işçiyle çalıştırmak
  gerekirse sayaç paylaşımlı bir yere (Redis) taşınmalı.
- **Ön yüzün otomatik testi yok.** Backend'in 56 testi var; arayüz her
  değişiklikte Playwright ile elle doğrulanıyor.
