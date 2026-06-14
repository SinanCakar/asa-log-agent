ASA Log Agent — Oyun-içi tribe-log okuyucu (Kurulum & Kullanım)
================================================================

NE YAPAR
  ARK tribe-log panelini kendi ekranindan OCR ile okur, olaylari (raid, kill,
  uye, tame, claim) Discord botuna gonderir. Yalniz "Day N, HH:MM:SS:" baslikli
  GERCEK tribe-log satirlarini gonderir; ekranindaki baska hicbir sey gonderilmez.
  ANTI-CHEAT GUVENLI: sadece ekran goruntusu alir; oyun process'ine/RAM'ine
  DOKUNMAZ. Sadece sen oynarken ve log paneli acikken calisir. Windows.

=== KURULUM (TEK DOSYA) ===
  1) ASA_LogAgent_Setup.exe indir ve calistir.
     (En son surum: github.com/SinanCakar/asa-log-agent/releases/latest)
  2) Sihirbaz adim adim sorar:
     - Kurulum klasoru (varsayilani birak yeter)
     - Bilesenler: "Tesseract-OCR 5.3.3" KURULU kalsin (OCR icin gerekli).
       Kurulum sirasinda Tesseract kendi penceresiyle acilir -> Install'a bas.
     - Token: Discord'da  /log key  yazip aldigin token'i yapistir.
     - Sunucu etiketi: orn. "the_island 7777".
  3) Biter. agent.ini otomatik yazilir (token, sunucu, Tesseract yolu hazir).
  Not: Token'i daha once almadiysan Discord'da once  /log key  calistir.

=== ILK KALIBRASYON (bir kez) ===
  Tribe-log panelini OKUYACAGI ekran bolgesini bir kez ayarla:
  1) ARK'i ac, Tribe Manager > LOG panelini ekrana getir.
  2) Baslat Menusu > "ASA Log Agent (Kalibrasyon)" calistir.
     (veya kurulum sonundaki "Simdi kalibre et" kutusu)
  3) Ekran goruntusu kaydedilir; konsol tam yolunu yazar. O resimde log
     panelinin sol-ust kosesi (x, y) ve eni x boyu (genislik, yukseklik).
  4) Bu 4 sayiyi  x y genislik yukseklik  olarak gir (bosluklu). region yazilir.

=== CALISTIRMA ===
  Baslat Menusu > "ASA Log Agent".
  - Once test: bir komut penceresinde  ASA_LogAgent.exe --dry  -> hicbir sey
    gondermeden, OCR'in log'u dogru okudugunu konsolda gosterir.
  - Dogruysa normal calistir -> olaylar Discord'a gider.
  Discord'da  /log channel #kanal  ile uyarilarin gidecegi kanali sec
  (secmezsen sadece /logs ile gorunur, anlik uyari dusmez).

=== DISCORD KOMUTLARI ===
  /log key            kisisel token uret (agent.ini'ye gir)
  /log channel #kanal uyari kanalini sec
  /log status         token/kanal/kural durumu
  /log ruleadd        regex -> severity kurali ekle
  /logs [saat]        son yakalanan tribe-log olaylari

=== AYARLAR (agent.ini) ===
  Konum: %LOCALAPPDATA%\ASALogAgent\agent.ini
  token, server_label, region, interval, fuzzy_threshold burada.
  Elle degistirip kaydedebilirsin; agent'i yeniden baslat.

=== KALDIRMA ===
  Ayarlar > Uygulamalar > "ASA Log Agent" > Kaldir.
  - Ayarlarin/verilerin (token dahil) silinsin mi diye sorar.
  - Tesseract'i da kaldirmak ister misin diye sorar (baska program kullanmiyorsan).

=== GIZLILIK ===
  Yalniz "Day N, HH:MM:SS:" basligiyla baslayan gercek tribe-log satirlari
  gonderilir. Menu/sohbet/ekran metni elenir. Ayni satir tekrar gonderilmez.
  Token'ini kimseyle paylasma (/log revoke ile iptal, /log key ile yenile).
