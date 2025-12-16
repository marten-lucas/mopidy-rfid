# mopidy-rfid

**Mopidy-Erweiterung für RFID-gesteuerte Musikwiedergabe auf dem Raspberry Pi**

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/)

## Funktionen

`mopidy-rfid` verwandelt deinen Raspberry Pi in eine RFID-gesteuerte Jukebox. Halte einen RFID-Tag (z.B. eine Karte oder Figur) an den RC522-Leser, und die verknüpfte Musik wird automatisch abgespielt.

### Features

- 🎵 **RFID-Tag-zu-Musik-Mapping**: Verknüpfe RFID-Tags mit Spotify-Tracks, lokalen Dateien, Playlists oder Alben
- 🔄 **Self-Healing SPI-Bus**: Automatischer Hardware-Reset bei Abstürzen des RC522-Readers (häufig am Pi Zero)
- 💡 **LED-Feedback**: Optionaler WS2812B LED-Ring zeigt Systemstatus und Tag-Erkennung
- 🌐 **Web-Admin-UI**: Modernes Materialize-basiertes Interface zum Verwalten der Mappings
- 🔍 **Mopidy-Library-Suche**: Durchsuche deine Musikbibliothek direkt im Web-UI
- ⚡ **WebSocket Live-Updates**: Echtzeitbenachrichtigungen bei Tag-Erkennung
- 🛠️ **Robuste Architektur**: Pykka Actor-Pattern, Thread-sichere Hardware-Zugriffe, SQLite-Mappings-DB

### Hardware-Unterstützung

- **RFID-Leser**: RC522 (SPI, mit SimpleMFRC522-Library)
- **LED-Ring**: WS2812B/NeoPixel (optional, GPIO 12/PWM0)
- **Status-LED**: Einzelne LED für Power-Button (optional, GPIO 13)
- **Getestet auf**: Raspberry Pi Zero, Pi 3/4

## Installation

### 1. Vorbereitung (Raspberry Pi)

**SPI aktivieren:**
```bash
sudo raspi-config
# -> Interface Options -> SPI -> Enable
```

**System-Pakete installieren:**
```bash
sudo apt update
sudo apt install python3-dev python3-pip build-essential
```

### 2. Mopidy installieren

```bash
# Mopidy aus offiziellen Repos
sudo apt install mopidy

# Oder via pip (neueste Version)
pip3 install Mopidy
```

### 3. mopidy-rfid installieren

**Von GitHub:**
```bash
cd /opt
sudo git clone https://github.com/marten-lucas/mopidy-rfid.git
cd mopidy-rfid
sudo pip3 install -e .
```

### 4. Hardware anschließen

**RC522 RFID-Leser (SPI):**
| RC522 Pin | Pi Pin (BCM) | Beschreibung |
|-----------|--------------|--------------|
| SDA       | GPIO 8 (CE0) | Chip Select  |
| SCK       | GPIO 11      | SPI Clock    |
| MOSI      | GPIO 10      | Master Out   |
| MISO      | GPIO 9       | Master In    |
| GND       | GND          | Ground       |
| RST       | GPIO 25      | Reset        |
| 3.3V      | 3.3V         | Stromversorgung |

**WS2812B LED-Ring (optional):**
- Data → GPIO 12 (PWM0)
- GND → GND
- 5V → 5V (externes Netzteil empfohlen für >8 LEDs)

## Konfiguration

Bearbeite `/etc/mopidy/mopidy.conf`:

```ini
[rfid]
enabled = true

# Hardware-Pins (BCM-Nummerierung)
pin_rst = 25
pin_button_led = 13

# LED-Ring (optional)
led_enabled = true
led_pin = 12
led_count = 16
led_brightness = 60

# Pfad zur Mappings-Datenbank (optional)
# mappings_db_path = /pfad/zur/mappings.db
```

## Nutzung

### 1. Mopidy starten

```bash
mopidy
```

### 2. Web-UI öffnen

Öffne im Browser: `http://<raspberry-pi-ip>:6680/rfid/`

### 3. RFID-Tag verknüpfen

1. Halte einen RFID-Tag an den Reader
2. Prüfe Mopidy-Logs für die Tag-ID
3. Trage Tag-ID und URI im Web-UI ein

### Spezielle Aktionen

- **`TOGGLE_PLAY`**: Play/Pause umschalten
- **`STOP`**: Wiedergabe stoppen

### Beispiel-URIs

- Spotify: `spotify:track:3n3Ppam7vgaVa1iaRUc9Lp`
- Lokale Datei: `local:track:musik.mp3`

## Entwicklung

### Tests ausführen

```bash
pytest --cov=mopidy_rfid
```

### Code-Qualität

```bash
ruff check .
ruff format .
pyright src
```

## Lizenz

Apache License 2.0

## Credits

Entwickelt von [Marten Lucas](mailto:marten.lucas@yahoo.de)
