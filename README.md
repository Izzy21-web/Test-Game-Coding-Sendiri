# AGENT DUTY

**[▶ MAIN SEKARANG DI BROWSER](https://izzy21-web.github.io/Test-Game-Coding-Sendiri/)**

Game FPS agen rahasia (raycasting) buatan sendiri dengan **Python + pygame**.
Semua grafik dan suara dibuat lewat kode. Tersedia versi PC dan versi web.

## Main di PC
```
pip install pygame numpy
python AGENT-DUTY.py
```
Multiplayer (LAN/internet) hanya ada di versi PC.

## Versi web
Berjalan di browser lewat [pygbag](https://github.com/pygame-web/pygbag) (Python dijalankan di WebAssembly).
Kodenya tetap Python. Halaman HTML-nya dibuat otomatis oleh pygbag.

- `AGENT-DUTY.py`  : file game asli, **tidak diubah**
- `buat_versi_web.py` : membuat `web/main.py` dari file asli (9 penyesuaian kecil, semua ditandai `[WEB]`)
- `web/main.py` : salinan khusus browser (hasil skrip di atas)

Buat ulang versi web setelah mengubah game:
```
python buat_versi_web.py
```
Coba di komputer sendiri:
```
pip install pygbag
pygbag web
```
lalu buka http://localhost:8000

## Terbitkan ke GitHub Pages
1. Push semua file ke GitHub (branch `main`).
2. Di repo: **Settings > Pages > Source: GitHub Actions**.
3. Tunggu tab **Actions** selesai. Alamatnya: `https://izzy21-web.github.io/Test-Game-Coding-Sendiri/`

## Catatan versi web
- Multiplayer dimatikan (browser tidak bisa membuka server/socket).
- Klik halaman sekali saat diminta supaya suara aktif.
- Kalau mouse tidak bisa dipakai untuk menengok, pakai panah kiri/kanan atau Q/E.
- Loading awal agak lama karena suara dibuat lewat kode.
