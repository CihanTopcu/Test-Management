Yazılı: bu arayüze dokunacak geliştiriciler için.

# Kanıt — arayüz

React 19 + TypeScript + Vite. Bileşen kütüphanesi yok; tasarım sistemi
`src/styles.css` içinde, CSS değişkenleriyle.

```bash
npm install
npm run dev      # http://localhost:5173, /api proxy'si 8010'a gider
npm run build    # tsc -b && vite build
```

## Tasarım dili

Renk, tipografi ve biçim DGPays ürün tasarımından alındı (Bakiye Transfer
Onayı ekranı). Değerler tahmin değil, o tasarımdan çıkarıldı:

| Token | Değer | Nereden |
|---|---|---|
| `--accent` | `#00A9CE` | birincil buton, aktif menü |
| `--accent-hover` | `#0880CE` | buton hover |
| `--accent-soft` | `#F2FBFD` | ikincil buton hover |
| `--text` | `#12263F` | başlıklar |
| `--text-dim` | `#536476` | menü, ikincil metin |
| `--text-faint` | `#A9B7C2` | bölüm etiketleri |
| `--border` | `#E2E5E7` | kenarlıklar |
| `--bg` | `#F6F8F9` | sayfa |
| `--surface-2` | `#EDF1F3` | hover yüzeyi |
| `--danger` / `--danger-ink` | `#F63E47` / `#820014` | uyarı, çıkış |
| `--ok` | `#52C41A` | başarı |
| `--radius` | `12px` | kart, buton, menü öğesi |
| `--shadow` | `0 4px 40px rgba(0,0,0,.05)` | kart gölgesi |

**Taşınmayan şey: yoğunluk.** O ekran tek sütunlu, 720px genişliğinde bir
onay sayfası; buradaki en büyük koşum 10.062 satır. Onun iç boşluklarını
almak ekrana sığanı yarıya indirirdi. Marka katmanı taşındı, bilgi yerleşimi
kaldı.

Karanlık tema aynı renk ailesinden türetildi (lacivert zemin, `#29C3E2`
vurgu) — ürün tasarımının karanlık teması yok.

## Tipografi

`Omnes, Inter, …` — Omnes DGPays'in marka fontu ve lisanslıdır, bu yüzden
depoda yok; kurulu olan makinede kullanılır. Arkasında **Inter** var ve
`public/fonts/` içinde uygulamayla birlikte geliyor.

Bu bilinçli: ürün tasarımı Inter'i `fonts.googleapis.com`'dan çekiyor, ama
Kanıt kapalı bir sunucuda çalışıyor. Dışarıya çıkamayan bir makinede font
sessizce Segoe'ye düşer ve kimsenin onaylamadığı bir arayüz ortaya çıkar.
İki dosya, 130 KB, değişken font olduğu için tüm ağırlıkları veriyor —
latin ve latin-ext, çünkü Türkçede `ğ` ve `ş` latin-ext'te.

## Marka

`src/components/Logo.tsx`. İşaret: kutusundan taşan bir onay. Sağ üst
köşedeki boşluk markanın kendisi — o olmasa her ikinci uygulamanın
gönderdiği "verified" rozeti olurdu. 16px'te boşluk kapanır ve yuvarlak
kare içinde bir onaya döner; doğru bozulma bu.

Favicon (`public/favicon.svg`) koyu değil indigo fayans üzerinde: sekme
çubuğu açık da koyu da olabilir, yalnızca yüksek kontrastlı bir fayans
ikisinde de okunur.
