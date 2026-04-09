# YTMEDIA - Youtube Media Downloader

**YTMedia** is a tool written with **Pyside6** and **Yt_dlp** to download youtube videos and turn them into various other formats through **FFmpeg**

---
## Features

- **Guided Wizard UI:** Step-by-step interface for easy navigation and use
- **Metadata preview**: Fetches video information like title, channel duration and others before downloading
- **Multiple format support**: Choose from all available quality/resolution options detected for video and audio
- **Multiple output formats** such as MP3, MKV, M4A, MP4...
- **Playlist support:** Download entire playlists with a single click
- **Download queue:** Queue multiple URLs for sequential downloading
- **Pause/Resume/Cancel/Retry:** Control your downloads with ease
- **Download history:** Keep track of all your downloaded media with timestamps and metadata
- **Custom output templates:** Define your own naming conventions for downloaded files
- **Cookies support:** Load a cookies.txt file to access age-restricted or region-locked content
- **Persistent settings:** Saves your preferences and configurations between sessions

---
## Requirements
- Python 3.10 or higher
- FFmpeg (Bundled or available in PATH)
- Yt_dlp
- PySide6
---
## Installation
**Install dependencies**
```bash
pip install -r requirements.txt
```
**Run with python**
```bash
python main.py
```