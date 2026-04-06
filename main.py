import os, re, sys, time, shutil, yt_dlp, platform

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QUrl, QByteArray
from PySide6.QtGui import QDesktopServices, QPixmap, QAction, QFont, QFontDatabase, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QComboBox, QFileDialog,
    QCheckBox, QSpinBox, QProgressBar, QTableWidget, QTableWidgetItem,
    QMessageBox, QHeaderView, QAbstractItemView, QMenu, QStackedWidget, QMainWindow
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
        settings_frame = QWidget()
        settings_frame.setObjectName("Card")
        settings_layout = QGridLayout(settings_frame)
        settings_layout.setVerticalSpacing(15)

        self.folder_input = QLineEdit(self.settings.value("last_folder", os.path.expanduser("~")))
        self.folder_input.setMinimumHeight(35)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setFont(load_font())
        self.browse_btn.clicked.connect(self.pick_folder)
        settings_layout_lbl = QLabel("Save to:")
        settings_layout_lbl.setFont(load_font())
        settings_layout.addWidget(settings_layout_lbl, 0, 0)
        settings_layout.addWidget(self.folder_input, 0, 1, 1, 2)
        settings_layout.addWidget(self.browse_btn, 0, 3)

        self.format_box = QComboBox()
        self.format_box.addItem("best audio/video (auto)", "")
        self.format_box.setMinimumHeight(35)
        self.convert_box = QComboBox()
        self.convert_box.addItems(["Extract Audio as MP3 (Default)", "Convert video to MP4", "Convert video to MKV", "No Conversion (WEBM)"])
        self.convert_box.setCurrentText(self.settings.value("convert_mode", "Extract Audio as MP3 (Default)"))
        self.convert_box.setMinimumHeight(35)
        settings_layout.addWidget(self.format_box, 1, 1)
        settings_layout_lbl_1 = QLabel("Quality Option:")
        settings_layout.addWidget(settings_layout_lbl_1, 1, 0)
        settings_layout.addWidget(self.format_box, 1, 1)
        settings_layout_lbl_2 = QLabel("Action:")
        settings_layout.addWidget(settings_layout_lbl_2, 1, 2)
        settings_layout.addWidget(self.convert_box, 1, 3)

        self.playlist_check = QCheckBox("Download entire playlist")
        self.playlist_check.setChecked(self.settings.value("playlist", "false") == "true")
        self.max_items = QSpinBox()
        self.max_items.setRange(0, 9999)
        self.max_items.setValue(int(self.settings.value("max_items", 0)))
        self.max_items.setPrefix("Max items (0=all): ")
        self.max_items.setMinimumHeight(35)
        self.mp3_bitrate_box = QComboBox()
        self.mp3_bitrate_box.addItems(["128", "192", "256", "320"])
        self.mp3_bitrate_box.setCurrentText(self.settings.value("mp3_bitrate", "192"))
        self.mp3_bitrate_box.setMinimumHeight(35)
        settings_layout.addWidget(self.playlist_check, 2, 0)
        settings_layout.addWidget(self.max_items, 2, 1)
        bitrate_lbl = QLabel("MP3 kbps:")
        bitrate_lbl.setFont(load_font())
        settings_layout.addWidget(bitrate_lbl, 2, 2)
        settings_layout.addWidget(self.mp3_bitrate_box, 2, 3)
        p2_layout.addWidget(settings_frame)

        # Advanced Settings
        adv_frame = QWidget()
        adv_frame.setObjectName("Card")
        adv_layout = QHBoxLayout(adv_frame)
        self.open_folder_check = QCheckBox("Open folder after")
        self.open_folder_check.setChecked(True)
        self.copy_path_check = QCheckBox("Copy path")
        self.template_input = QLineEdit(self.settings.value("template", "%(title)s.%(ext)s"))
        self.template_input.setPlaceholderText("Name template")
        self.cookies_input = QLineEdit(self.settings.value("cookies", ""))
        self.cookies_input.setPlaceholderText("Cookies.txt path")
        self.cookies_btn = QPushButton("Cookies..")
        self.cookies_btn.clicked.connect(self.pick_cookies)

        adv_layout.addWidget(self.open_folder_check)
        adv_layout.addWidget(self.copy_path_check)
        adv_layout.addWidget(QLabel(" Template:"))
        adv_layout.addWidget(self.template_input)
        adv_layout.addWidget(self.cookies_input)
        adv_layout.addWidget(self.cookies_btn)
        p2_layout.addWidget(adv_frame)

        p2_layout.addStretch()

        p2_controls = QHBoxLayout()
        self.back_btn1 = QPushButton("🡄 Back")
        self.back_btn1.setMinimumHeight(40)
        self.back_btn1.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        self.download_btn = QPushButton("Start Download ➔")
        self.download_btn.setObjectName("PrimaryButton")
        self.download_btn.setMinimumHeight(40)
        self.download_btn.clicked.connect(self.start_download)
        p2_controls.addWidget(self.back_btn1, 1)
        p2_controls.addWidget(self.download_btn, 3)
        p2_layout.addLayout(p2_controls)

        self.stacked_widget.addWidget(self.page2)

        # --- PAGE 3: Download progress and logs ---
        self.page3 = QWidget()
        p3_layout = QVBoxLayout(self.page3)

        prog_frame = QWidget()
        prog_frame.setObjectName("Card")
        prog_layout = QVBoxLayout(prog_frame)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setMinimumHeight(30)
        self.stats_label = QLabel("Time Remaining: -- | Downloaded: -- / -- | Speed: --")
        self.stats_label.setFont(load_font())
        self.stats_label.setAlignment(Qt.AlignCenter)
        prog_layout.addWidget(self.progress)
        prog_layout.addWidget(self.stats_label)
        p3_layout.addWidget(prog_frame)

        # Queue
        queue_lbl = QLabel("<b>Download Queue</b>")
        queue_lbl.setFont(load_font())
        self.queue_table = QTableWidget(0, 2)
        self.queue_table.setHorizontalHeaderLabels(["URL", "Requested Format"])
        self.queue_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.remove_queue_btn = QPushButton("Remove selected from queue")
        self.remove_queue_btn.clicked.connect(self.remove_selected_queue_item)

        p3_layout.addWidget(queue_lbl)
        p3_layout.addWidget(self.queue_table, 1)
        p3_layout.addWidget(self.remove_queue_btn)

        log_lbl = QLabel("<b>Export Logs</b>")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        p3_layout.addWidget(log_lbl)
        p3_layout.addWidget(self.log, 2)

        p3_controls = QHBoxLayout()
        self.pause_btn = QPushButton("Pause")
        self.resume_btn = QPushButton("Resume")
        self.cancel_btn = QPushButton("Cancel")
        self.retry_btn = QPushButton("Retry")
        for b in [self.pause_btn, self.resume_btn, self.cancel_btn, self.retry_btn]:
            b.setMinimumHeight(40)
        self.pause_btn.clicked.connect(self.pause_current)
        self.resume_btn.clicked.connect(self.resume_current)
        self.cancel_btn.clicked.connect(self.cancel_current)
        self.retry_btn.clicked.connect(self.retry_last)
        for b in (self.pause_btn, self.resume_btn, self.cancel_btn):
            b.setEnabled(False)

        p3_controls.addWidget(self.pause_btn)
        p3_controls.addWidget(self.resume_btn)
        p3_controls.addWidget(self.cancel_btn)
        p3_controls.addWidget(self.retry_btn)
        p3_layout.addLayout(p3_controls)

        self.stacked_widget.addWidget(self.page3)

        # --- PAGE 4: Success view ---
        self.page4 = QWidget()
        p4_layout = QVBoxLayout(self.page4)
        p4_layout.setAlignment(Qt.AlignCenter)

        self.success_icon = QLabel("✅")
        font_icon = self.success_icon.font()
        font_icon.setPointSize(60)
        self.success_icon.setFont(font_icon)
        self.success_icon.setAlignment(Qt.AlignCenter)

        self.success_title = QLabel("Video Exported Successfully!")
        font_title = load_font()
        font_title.setPointSize(24)
        font_title.setBold(True)
        self.success_title.setFont(font_title)
        self.success_title.setAlignment(Qt.AlignCenter)

        self.success_path = QLabel("Path...")
        self.success_path.setFont(load_font())
        self.success_path.setAlignment(Qt.AlignCenter)
        self.success_path.setStyleSheet("""
            color: #8ab4f8;
            margin-top: 15px;
            margin-bottom: 30px;
        """)

        p4_btns = QHBoxLayout()
        self.open_exported_btn = QPushButton("Open Folder")
        self.open_exported_btn.setFont(load_font())
        self.open_exported_btn.setMinimumHeight(50)

        self.new_download_btn = QPushButton("Start Another Download")
        self.new_download_btn.setFont(load_font())
        self.new_download_btn.setObjectName("PrimaryButton")
        self.new_download_btn.setMinimumHeight(50)
        self.new_download_btn.clicked.connect(self.reset_to_start)

        p4_btns.addWidget(self.open_exported_btn, 1)
        p4_btns.addWidget(self.new_download_btn, 2)

        p4_layout.addWidget(self.success_icon)
        p4_layout.addWidget(self.success_title)
        p4_layout.addWidget(self.success_path)
        p4_layout.addLayout(p4_btns)

        self.stacked_widget.addWidget(self.page4)

        self.setLayout(root)
        self.restoreGeometry(self.settings.value("geometry", QByteArray()))
app = QApplication(sys.argv)
app.setWindowIcon(QIcon("icon.ico"))
app.setFont(load_font())
app.setStyleSheet(f"""
    QWidget {{
        background-color: #202124;
        color: f1f3f4;
        font-family: {load_font().family()};
        font-size: 10pt;
    }}
    #Card {{
        background-color: #2b2b2b;
        border-radius: 8px;
        border: 1px solid #3c3c3c;
        font-family: {load_font().family()};
    }}
    QLineEdit, QTextEdit , QComboBox, QSpinBox , QTableWidget {{
        background-color: #303134;
        color: #e8eaed;
        border: 1px solid #5f6368; 
        border-radius: 5px; 
        padding: 5px 12px; 
        font-family: {load_font().family()};
        font-weight: bold;
    }}
    QPushButton:hover {{ 
        background-color: #4a4d51; 
    }}
    QPushButton:pressed {{
        background-color: #55585d; 
    }}
    QPushButton:disabled {{ 
        color: #888; 
        border: 1px solid #444; 
        background: #2f2f2f; 
    }}
    #PrimaryButton {{
        background-color: #4169E1; 
        color: white; 
        border: none; 
    }}
    #PrimaryButton:hover {{ 
        background-color: #2754e3; 
    }}
    QProgressBar {{ 
        border: 1px solid #5f6368; 
        border-radius: 5px; 
        text-align: center; 
        font-weight: bold; 
        background: #303134; 
    }}
    QProgressBar::chunk {{ 
        background-color: #34a853; 
        border-radius: 4px; 
    }}
    QTableWidget {{ 
        gridline-color: #444; 
        border: 1px solid #444;
        font-family: {load_font().family()}; 
    }}
    QHeaderView::section {{ 
        background-color: #3c4043; 
        padding: 4px; 
        border: 1px solid #444; 
        font-weight: bold; 
        font-family: {load_font().family()};
    }}
    QTableWidget::item:selected {{ 
        background-color: #4169E1; 
        color: white; 
        font-family: {load_font().family()};
    }}
""")

window = App()
window.show()
sys.exit(app.exec())