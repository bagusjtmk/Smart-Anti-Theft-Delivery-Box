# SmartBox — Smart Anti-Theft Delivery Box (IoT)

Kotak paket pintar: HP Android di dalam kotak mendeteksi **guncangan** (accelerometer) dan
**tutup dibuka** (light/proximity), lalu HP pemilik di dalam rumah **bergetar + berbunyi**.

```
Edge 1 (HP di kotak)         MQTT Broker (HiveMQ, TLS 8883)        Laptop: detector + dashboard
 accel + light/proximity ──► smartbox/<ID>/edge/box1/telemetry ──► rules.py (sensor fusion)
                                                                     │  status (retained) ──► Dashboard (WSS 8884)
Edge 2 (HP pemilik)      ◄── smartbox/<ID>/alerts ◄──────────────────┘  control (ARM/DISARM/ACK) ◄── Dashboard
 termux-vibrate/notification/tts
```

## Pemenuhan ketentuan tugas
| Ketentuan | Implementasi |
|---|---|
| 2 edge device | `box_node.py` (Edge 1), `owner_node.py` (Edge 2) — HP Android |
| 2 sensor | Accelerometer + Light (atau Proximity) di Edge 1 |
| 2 data processing | A) Motion RMS (`shared/processing.py::motion_rms`) · B) Threshold + hysteresis state transition tutup (`LidTracker`) |
| Algoritma | Rule-based sensor fusion + latching (`nodes/detector_service/rules.py`) |
| Protokol cloud | MQTT over TLS, HiveMQ publik `broker.hivemq.com:8883` |
| Dashboard | `dashboard/index.html`, disajikan detector di LAN (port 8000) |

## Status keamanan
| Kondisi | Status |
|---|---|
| DISARM | `SAFE` |
| ARM, tutup tertutup, diam | `SECURE` |
| ARM, tutup tertutup, RMS ≥ `TAMPER_RMS` | `TAMPER_ALERT` (ditahan `ALERT_HOLD_S` detik) |
| ARM, tutup terbuka | `ILLEGAL_OPEN` (ditahan sampai **ACK** / **DISARM**) |

## Setup
1. **Termux & Termux:API** dari F-Droid di kedua HP → `pkg update; pkg install python git termux-api; pip install paho-mqtt python-dotenv`
2. Cek sensor: `termux-sensor -l` (harus ada Accelerometer + Light Sensor / Proximity).
3. `git clone <repo-kamu>; cd smart-delivery-box; cp .env.example .env` → ganti **PROJECT_ID** (unik!). Pakai `.env` yang sama di semua perangkat.
4. Laptop: `pip install -r requirements.txt`

## Menjalankan (urutan)
```bash
python detector.py                 # 1. Laptop → dashboard http://<ip-laptop>:8000
python owner_node.py               # 2. HP Pemilik (Termux)
python box_node.py                 # 3. HP di kotak (Termux)
```
Tanpa HP (latihan di laptop): `python box_node.py --source simulator --scenario demo`
(skenario: `still`, `shake`, `open`, `demo` = siklus otomatis 60 detik) dan `python owner_node.py --source simulator`.

Kontrol dari konsol `owner_node.py`: `a`=ARM `d`=DISARM `k`=ACK `t`=test alarm `q`=keluar.

## Pemasangan HP di kotak
- **light** (default): HP di dalam kotak tertutup rapat → gelap (~0–5 lux); tutup dibuka → lux naik. Sesuaikan `LIGHT_OPEN_LUX`/`LIGHT_CLOSE_LUX` dengan kondisi ruangan.
- **proximity**: hadapkan sensor proximity (dekat earpiece) ke tutup; tertutup = dekat (0 cm), terbuka = jauh. Banyak HP hanya melaporkan 0 atau ±5 cm. Set `LID_SENSOR=proximity`.
- Matikan auto-lock layar / beri izin Termux:API, dan jalankan `termux-wake-lock` agar proses tidak dimatikan Android.

## Skenario pengujian (untuk dokumentasi/video)
1. ARM, kotak diam, tutup tertutup → `SECURE`
2. Ketuk/guncang kotak → `TAMPER_ALERT` → HP pemilik getar + notifikasi + suara
3. Buka tutup → `ILLEGAL_OPEN`; tutup lagi → tetap `ILLEGAL_OPEN` sampai ACK
4. DISARM → `SAFE` (ambil paket tanpa alarm), lalu ARM lagi
5. Matikan `box_node.py` → dashboard: telemetri *offline* setelah `STALE_S` detik

## Catatan keamanan
Broker publik dipakai bersama: **PROJECT_ID harus unik**, jangan kirim data rahasia. Isi `CONTROL_TOKEN`
agar hanya yang tahu token bisa ARM/DISARM (token dimasukkan di dashboard → Pengaturan koneksi).
Untuk produk nyata gunakan broker privat dengan username/password + ACL.

## Struktur
```
detector.py · box_node.py · owner_node.py · .env.example · requirements.txt
shared/   config, sensors, processing, messages, mqtt_client, edge_runner, alarm
nodes/detector_service/   rules.py (fusion), main.py (service), dashboard_server.py
dashboard/index.html      tests/test_core.py  (python -m unittest discover -s tests)
```
