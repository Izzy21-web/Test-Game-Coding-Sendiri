"""
buat_versi_web.py  -  membuat versi WEB dari AGENT-DUTY.py TANPA mengubah file aslinya.

Cara pakai (VS Code / terminal), taruh file ini di folder yang sama dengan AGENT-DUTY.py:
    python buat_versi_web.py
Hasil: folder  web/  berisi  main.py  (salinan yang disesuaikan untuk browser).
File AGENT-DUTY.py TIDAK diubah sama sekali (hanya dibaca).
"""
import os, sys

SUMBER = "AGENT-DUTY.py"
TUJUAN = os.path.join("web", "main.py")

# (teks asli, teks pengganti, penjelasan) - tiap teks asli harus ada TEPAT 1 kali
PATCH = [
 ("import math, random, os, json, socket, time, threading, ipaddress\n",
  "import asyncio, math, random, os, json, time, ipaddress             # [WEB] asyncio dibutuhkan pygbag\n"
  "try: import socket, threading                                       # [WEB] di browser tidak dipakai (multiplayer dimatikan)\n"
  "except Exception: socket = threading = None\n"
  "import sys\n"
  "WEB = sys.platform == \"emscripten\"                                  # [WEB] True kalau jalan di browser\n",
  "import untuk web"),

 ('else os.path.dirname(os.path.abspath(__file__)), "agent_duty_settings.json")',
  'else ("." if WEB else os.path.dirname(os.path.abspath(__file__))), "agent_duty_settings.json")',
  "lokasi simpan pengaturan"),

 ("    if not 0 <= i < len(RESF): return None\n",
  "    if WEB: return 0, (VWD, VHT)                # [WEB] ukuran layar dikunci 960x600, browser yang mengatur skalanya\n"
  "    if not 0 <= i < len(RESF): return None\n",
  "ukuran layar"),

 ('            elif act == 2: S.update(mode="mp", sel=0, msg="")\n',
  '            elif act == 2:\n'
  '                if WEB: S["msg"] = "Multiplayer tidak tersedia di versi web (browser tidak bisa membuka server). Pakai versi PC untuk multiplayer."\n'
  '                else: S.update(mode="mp", sel=0, msg="")\n',
  "multiplayer dimatikan di web"),

 ("            else: return False\n        elif m == \"players\":",
  "            elif not WEB: return False                              # [WEB] tombol keluar tidak berlaku di browser\n        elif m == \"players\":",
  "tombol keluar"),

 ('if S["mode"] == "main": run = False',
  'if S["mode"] == "main": run = WEB',
  "ESC di menu utama tidak menutup game di web"),

 ("def main():\n    global LIGHT, FLICK, MPSTART",
  "async def main():                               # [WEB] async supaya browser tidak hang\n    global LIGHT, FLICK, MPSTART",
  "main jadi async"),

 ("        present(); frames += 1\n",
  "        present(); frames += 1\n        await asyncio.sleep(0)                                    # [WEB] beri waktu ke browser tiap frame\n",
  "jeda per frame"),

 ('if __name__ == "__main__":\n    try:\n        main()\n    except Exception:\n        import traceback; traceback.print_exc()\n        input("\\nTerjadi error di atas. Tekan ENTER untuk menutup...")',
  'async def _jalan():\n    try:\n        await main()\n    except Exception:\n        import traceback; traceback.print_exc()\n        if not WEB: input("\\nTerjadi error di atas. Tekan ENTER untuk menutup...")\nasyncio.run(_jalan())                           # [WEB] pygbag butuh baris ini di paling bawah',
  "cara memulai game"),
]

def main():
    if not os.path.exists(SUMBER):
        sys.exit(f"File {SUMBER} tidak ditemukan. Taruh skrip ini di folder yang sama dengan {SUMBER}.")
    with open(SUMBER, "r", encoding="utf-8", newline="") as f:
        kode = f.read().replace("\r\n", "\n")
    for asli, baru, ket in PATCH:
        n = kode.count(asli)
        if n != 1:
            sys.exit(f"GAGAL pada '{ket}': teks asli ditemukan {n} kali (harus 1). File game mungkin sudah berubah dari versi yang saya baca.")
        kode = kode.replace(asli, baru)
    os.makedirs("web", exist_ok=True)
    with open(TUJUAN, "w", encoding="utf-8", newline="\n") as f:
        f.write(kode)
    print(f"Selesai! {TUJUAN} sudah dibuat ({len(PATCH)} penyesuaian). {SUMBER} tidak diubah.")

main()
