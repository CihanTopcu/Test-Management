# Geçiş Planı

TestRail'den kendi sistemimize geçiş adımları. Hedef: ekibin bir sabah
TestRail yerine yeni adrese girmesi ve hiçbir şeyin eksik olmaması.

Okuyucu: geçişi yürütecek kişi (bir kişi, birkaç saat).

---

## Geçişten önce

Bunlar geçiş gününden **önce** bitmiş olmalı:

- [ ] Sunucuya kurulum yapıldı, `DEPLOY.md` izlendi
- [ ] Tam göç yüklendi, `verify.py` temiz geçti, `audit.py` 0 hata verdi
- [ ] Kullanıcılara parola tanımlandı — **TestRail parolaları taşınamaz**,
      12 hesabın 11'inde parola yok
- [ ] Roller gözden geçirildi (Yönetim → Kullanıcılar ve Roller)
- [ ] En az bir otomasyon işi yeni API'ye bağlanıp deneme sonucu yazdı
- [ ] Yedekleme cron'u kuruldu ve bir kez geri yükleme denendi
- [ ] Ekipten 2-3 kişi sistemi bir hafta paralel kullandı

---

## Geçiş günü

Toplam süre: **yaklaşık 1,5–2 saat.** Çoğu bekleme.

### 1. Duyuru (T-1 gün)

TestRail'in ertesi gün saat X'te salt okunur olacağını duyurun. Değişiklik
yapan herkesin o saatten önce işini bitirmesi gerekir.

### 2. TestRail'i dondurun (T+0)

TestRail → Administration → Users & Roles → herkesin rolünü geçici olarak
**Read-only** yapın. Kendi hesabınız Admin kalsın; delta çekmek için API
erişimi lazım.

Dondurma anını **not alın** — delta bu saatten itibaren çalışacak.

### 3. Delta çekin (T+5dk, ~20–40 dk)

```bash
cd /opt/test-yonetimi
python migration/delta.py --since 2026-10-15T09:00 --load
```

Son tam dump'tan sonra değişen case'leri, yeni koşumları ve sonuçları alır,
ardından yükleyiciyi çalıştırır. Yükleyici idempotent olduğu için tekrar
çalıştırmak kayıt çoğaltmaz.

### 4. Karşılaştırın (T+45dk, ~15 dk)

```bash
python migration/delta.py --report
python migration/verify.py
python migration/audit.py
```

`--report` proje proje TestRail ile bizim sayıları yan yana koyar.

| Fark | Anlamı | Yapılacak |
|---|---|---|
| 0 | Her şey yerinde | Devam |
| Pozitif | TestRail'de yeni kayıt var | Delta'yı tekrar çalıştırın |
| Negatif | TestRail'de kayıt **silinmiş** | Elle inceleyin (aşağıya bakın) |

**Silme işlemleri API'den görünmez.** TestRail silinen kayıtları bildirmez;
dondurma penceresinde biri bir case sildiyse bizde durmaya devam eder.
Negatif fark tam olarak bunu gösterir. Genelde zararsızdır — silinen case
zaten kullanılmıyordu — ama rapor sessiz kalmaktansa farkı söyler.

### 5. Yönlendirin (T+60dk)

- DNS veya iç link: `testrail` kısayollarını yeni adrese çevirin
- Jenkins/JMeter işlerinde base URL ve token'ı değiştirin
- Jira'daki TestRail linkleri **çalışmaya devam eder** — case id'leri
  korundu, `C15477` hâlâ aynı case

### 6. Duyurun (T+75dk)

Yeni adres, giriş bilgileri, ve şu iki notu paylaşın:

- Parolalar taşınamadı, ilk girişte yöneticiden parola isteyin
- Arşivlenmiş koşumlar Koşumlar → Arşiv sekmesinde

---

## Geri dönüş

İlk hafta TestRail aboneliğini **kapatmayın**. Bir sorun çıkarsa:

1. TestRail'de rolleri eski haline getirin — 5 dakika, veri kaybı yok
2. Yeni sistemde geçiş sonrası girilen sonuçlar kalır; TestRail'e geri
   taşınması gerekiyorsa `migration/` araçları ters yönde çalışmaz, elle
   girilmesi gerekir

Bu yüzden ilk günlerde iki sisteme birden yazmak yerine tek yöne geçmek daha
güvenli: geri dönüş, yalnız yeni sistemde ne kadar az iş yapıldıysa o kadar
ucuz.

---

## Geçişten sonra

### İlk hafta

- [ ] Günlük yedeğin gerçekten alındığını kontrol edin
- [ ] `docker compose logs api` içinde 500 hatası var mı
- [ ] Otomasyon işlerinin sonuç yazdığını doğrulayın
- [ ] Kullanıcılardan gelen "şunu bulamıyorum" geri bildirimlerini toplayın

### İlk ay

- [ ] TestRail aboneliğini salt okunur arşiv olarak bir süre daha tutun
- [ ] 917 erişilemeyen gömülü görsel için karar: tarayıcı çerezi ile kurtarma
      şansı yalnızca abonelik sürerken var
- [ ] HTTPS ve ters vekil kurulumu (`DEPLOY.md` bölüm 8)
- [ ] Alembic devreye alınması

### Abonelik kapatılmadan önce son kontrol

```bash
python migration/delta.py --report     # son bir karşılaştırma
./ops/backup.sh                        # kapatma öncesi yedek
```

Abonelik kapandıktan sonra TestRail'den **hiçbir şey** alınamaz. Bu son
yedeği ayrı bir yerde saklayın.

---

## Bilinen eksikler

Geçişle birlikte kaybolacak, kabul edilmiş kalemler:

| Ne | Neden | Etki |
|---|---|---|
| 917 gömülü görsel | TestRail API'si UUID'li görselleri vermiyor | 416 case'te açıklama görseli eksik |
| Kullanıcı parolaları | Hiçbir uçtan çıkmıyor | Herkese yeni parola tanımlanmalı |
| 2 kayıtlı rapor tanımı | `get_reports` boş dönüyor | Rapor motoru zaten canlı veriden üretiyor |
| TestRail denetim günlüğü | API'de yok | Case geçmişi taşındı, sistem günlüğü taşınmadı |
| Kişisel tercihler, To-Do | API'de yok | Yeni sistemde yeniden kurulur |
