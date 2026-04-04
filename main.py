import os, re, sys, time, shutil, yt_dlp, platform

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QUrl, QByteArray
from PySide6.QtGui import QDesktopServices, QPixmap, QAction, QFont, QFontDatabase, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QComboBox, QFileDialog,
    QCheckBox, QSpinBox, QProgressBar, QTableWidget, QTableWidgetItem,
    QMessageBox, QHeaderView, QAbstractItemView, QMenu, QStackedWidget
)

#Load the font ttf
font_id = QFontDatabase.addApplicationFont("font.ttf")
def load_font():
    if font_id != -1:
        family_names = QFontDatabase.applicationFontFamilies(font_id)
        if family_names:
            family = family_names[0]
            font = QFont(family, 16)
            font.setBold(True)
            return font
        else:
            print("Font loaded, but no family names found.")
    else:
        print("Failed to load font.")
    return QFont("Arial", 16, QFont.Bold)

def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

base_dir = get_base_path()

IS_WINDOWS = platform.platform() == 'Windows'

class DownloadThread(QThread):
    log_signal = Signal(str)
    progress_signal = Signal(dict)
    done_signal = Signal(dict)
    error_signal = Signal(str)
    metadata_signal = Signal(dict)
    status_signal = Signal(str)

    def __init__(self, task, mode="download"):
        super().__init__()
        self.task = dict(task or {})
        self.mode = mode
        self._paused = False
        self._cancelled = False
        self._last_path = ""

    def pause(self):
        self._paused = True
        self.status_signal.emit("Paused (UI throttle)")

    def resume(self):
        self._paused = False
        self.status_signal.emit("Downloading")

    def cancel(self):
        self._cancelled = True
        self.status_signal.emit("Cancelling..")

    def _human_error(self, err:Exception):
        s = str(err).lower()
        if "ffmpeg" in s:
            return "FFmpeg not found/configured. Put ffmpeg.exe and ffprobe.exe in the 'ffmpeg/bin' folder in the app root directory."
        if "network" in s or "timed out" in s or "connection" in s or "dns" in s:
            return "Network error. Check your connection and try again."
        if "login" in s or "sign in" in s or "private" in s or "members" in s or "forbidden" in s:
            return "Restricted content. Try a valid cookies file."
        if "javascript" in s or "runtime" in s:
            return "Javascript runtime error. Ensure deno is installed configured correctly."
        return f"Download error: {err}"

    def _parse_percent(self, pct_str: str) -> float:
        if not pct_str:
            return 0.0
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%", pct_str.strip())
        return float(m.group(1)) if m else 0.0

    def _resolve_deno_binary(self) -> str:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        canditates = [base_dir]
        if hasattr(sys, "_MEIPASS"):
            canditates.append(sys._MEIPASS)
        for root in canditates:
            deno_path = os.path.join(root, "deno", "deno.exe")
            if os.path.isfile(deno_path):
                return deno_path
        return ""

    def _resolve_ffmpeg_location(self) -> str:
        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        canditates = [base_dir]
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            canditates.append(meipass)
        for root in canditates:
            bin_dir = os.path.join(root, "ffmpeg","bin")
            ffmpeg_exe = os.path.join(bin_dir, "ffmpeg.exe")
            ffprobe_exe = os.path.join(bin_dir, "ffprobe.exe")
            if os.path.isfile(ffmpeg_exe) and os.path.isfile(ffprobe_exe):
                return bin_dir
        return base_dir

    def run(self):
        def hook(d):
            if self._cancelled:
                raise Exception("Cancelled by user")
            while self._paused and not self._cancelled:
                time.sleep(0.15)
            if d.get("status") == "downloading":
                pct_raw = d.get("_percent_str", "")
                payload = {
                    "pct_raw": pct_raw.strip(),
                    "pct_val": self._parse_percent(pct_raw),
                    "eta": str(d.get("_eta_str", "")).strip(),
                    "downloaded": str(d.get("_downloaded_bytes_str", "")).strip(),
                    "total": str(d.get("_total_bytes_str", d.get("_total_bytes_estimate_str", ""))).strip(),
                }
                self.progress_signal.emit(payload)
            elif d.get("status") == "finished":
                self._last_path = d.get("filename") or self._last_path
                self.log_signal.emit("Download finished, post-processing...")

        try:
            url = self.task["url"]
            ffmpeg_location = self._resolve_ffmpeg_location()
            deno_location = self._resolve_deno_binary()

            if deno_location:
                deno_dir = os.path.dirname(deno_location)
                current_path = os.environ.get("PATH", "")
                if deno_dir not in current_path:
                    os.environ["PATH"] = deno_dir + os.pathsep + current_path

            if self.mode == "metadata":
                meta_opts = {
                    "quiet": True,
                    "skip_download": True,
                    "noplaylist": False,
                    "ffmpeg_location": ffmpeg_location
                }
                with yt_dlp.YoutubeDL(meta_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                self.metadata_signal.emit(url, download=False)
                self.metadata_signal.emit(info or {})
                return

            ydl_opts = {
                "progress_hooks": [hook],
                "outtmpl": os.path.join(self.task["folder"], self.task["template"]),
                "noplaylist": not self.task["playlist"],
                "retries": 3,
                "quiet": True,
                "ffmpeg_location": ffmpeg_location
            }

            if self.task["max_items"] > 0:
                ydl_opts["playlistend"] = self.task["max_items"]
            if self.task["cookies"]:
                ydl_opts["cookiefile"] = self.task["cookies"]

            selected = self.task.get("format_id")
            convert_mode = self.task.get("convert_mode", "Extract audio as MP3(Default)")
            post = []
            if selected == "audio_mp3":
                ydl_opts["format"] = "bestaudio/best"
                post.append({
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": self.task.get("mp3_bitrate", "192")
                })
            elif selected == "audio_m4a":
                ydl_opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
            elif selected:
                ydl_opts["format"] = selected
            else:
                if convert_mode == "Convert to MP4":
                    ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
                elif convert_mode == "Extract audio as MP3(Default)":
                    ydl_opts["format"] = "bestaudio/best"
                    post.append({
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": self.task.get("mp3_bitrate", "192")
                    })
                else:
                    ydl_opts["format"] = "bestvideo+bestaudio/best"

            if convert_mode == "Convert to MP4":
                post.append({"key": "FFmpegVideoConvertor", "preferredformat": "mp4"})
                ydl_opts.setdefault("postprocessor_args", {})["FFmpegVideoConvertor"] = ["-c:a", "aac"]
            elif convert_mode == "Convert to MKV":
                post.append({"key": "FFmpegVideoConvertor", "preferredformat": "mkv"})
            if post:
                ydl_opts["postprocessors"] = post

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True) or {}
                title = info.get("title", "Unknown")
                prepared = ydl.prepare_filename(info) if info else ""
                final_path = self._last_path or prepared
            self.done_signal.emit({"output_path": final_path or "", "url": url, "title": title})

        except Exception as e:
            self.error_signal.emit("Download cancelled" if "Cancelled by user" in str(e) else self._human_error(e))

class App(QWidget):
    def __init__(self):
        super().__init__()

        self.settings = QSettings("YTMedia", "YTMedia")
        self.thread = None
        self.meta_thread = None
        self.queue = []
        self.current_task = None
        self.last_error_task = None
        self.current_info = {}
        self.net = QNetworkAccessManager(self)
        self._clear_logs_before_next_start = False

        self.setWindowTitle("YTMedia - Youtube Video Dowloader by Qorym")
        self.setMinimumSize(950, 800)

        root = QVBoxLayout()
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 20)

        #Title, Header
        load_font()
        header_label = QLabel("YT2MP Downloader Wizard")
        header_label.setFont(load_font())
        header_label.setAlignment(Qt.AlignCenter)
        root.addWidget(header_label)

        self.stacked_widget = QStackedWidget()
        root.addWidget(self.stacked_widget)

        # --- PAGE 1: Link upload ---
        self.page1 = QWidget()
        p1_layout = QVBoxLayout(self.page1)
        p1_layout.setAlignment(Qt.AlignTop)

        # URL row
        url_frame = QWidget()
        url_frame.setObjectName("Card")
        url_layout = QVBoxLayout(url_frame)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste your Youtube video or playlist url here")
        self.url_input.setMinimumHeight(40)

        self.preview_btn = QPushButton("Next Step ➔")
        self.preview_btn.setObjectName("PrimaryButton")
        self.preview_btn.setMinimumHeight(40)
        self.preview_btn.setToolTip("Validate the link and find avaiable quality options")
        self.preview_btn.clicked.connect(self.preview_url)

        url_row_lbl = QLabel("Video/Playlist Link:")
        url_row_lbl.setFont(load_font())
        url_row.addWidget(url_row_lbl)
        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.preview_btn)
        url_layout.addLayout(url_row)

        self.loading_label = QLabel("")
        self.loading_label.setStyleSheet("color: #8ab4f8; font-weight: bold;")
        self.loading_label.setFont(load_font())
        url_layout.addWidget(self.loading_label)
        p1_layout.addWidget(url_frame)

        p1_layout.addSpacing(20)

        # Page 1's HIstory table
        hist_lbl = QLabel("<b>Past Downloads</b>")
        hist_lbl.setFont(load_font())
        self.history_table = QTableWidget(0, 3)
        self.history_table.setFont(load_font())
        self.history_table.setHorizontalHeaderLabels(["Title", "Status", "Time"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.history_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history_table.customContextMenuRequested.connect(self.show_history_menu)
        p1_layout.addWidget(hist_lbl)
        p1_layout.addWidget(self.history_table)

        self.stacked_widget.addWidget(self.page1)

        # --- PAGE 2: Options and preview ---
        self.page2 = QWidget()
        p2_layout = QVBoxLayout(self.page2)
        p2_layout.setAlignment(Qt.AlignTop)

        # MEtadata
        meta_frame = QWidget()
        meta_frame.setObjectName("Card")
        meta_row = QHBoxLayout(meta_frame)
        self.thumb_label = QLabel("Thumbnail\nHere")
        self.thumb_label.setFont(load_font())
        self.thumb_label.setFixedSize(240, 135)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("background: #2b2b2b; color: #888; border: 1px solid #444; border-radius: 8px;")
        self.meta_label = QLabel("<b>Status</b> Ready\n<br><br><b>Video details:</b>\nTitle: -- \nDuration: -- \nChannel: --")
        self.meta_label.setFont(load_font())
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet("padding: 10px;")
        meta_row.addWidget(self.thumb_label)
        meta_row.addWidget(self.meta_label, 1)
        p2_layout.addWidget(meta_frame)

        # Settings
