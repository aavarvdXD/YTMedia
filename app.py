import os, re, sys, time, shutil, yt_dlp, platform
from download import DownloadThread

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
def font():
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
        font()
        header_label = QLabel("YT2MP Downloader Wizard")
        header_label.setFont(font())
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
        url_row_lbl.setFont(font())
        url_row.addWidget(url_row_lbl)
        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.preview_btn)
        url_layout.addLayout(url_row)

        self.loading_label = QLabel("")
        self.loading_label.setStyleSheet("color: #8ab4f8; font-weight: bold;")
        self.loading_label.setFont(font())
        url_layout.addWidget(self.loading_label)
        p1_layout.addWidget(url_frame)

        p1_layout.addSpacing(20)

        # Page 1's HIstory table
        hist_lbl = QLabel("<b>Past Downloads</b>")
        hist_lbl.setFont(font())
        self.history_table = QTableWidget(0, 3)
        self.history_table.setFont(font())
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
        self.thumb_label.setFont(font())
        self.thumb_label.setFixedSize(240, 135)
        self.thumb_label.setAlignment(Qt.AlignCenter)
        self.thumb_label.setStyleSheet("background: #2b2b2b; color: #888; border: 1px solid #444; border-radius: 8px;")
        self.meta_label = QLabel("<b>Status</b> Ready\n<br><br><b>Video details:</b>\nTitle: -- \nDuration: -- \nChannel: --")
        self.meta_label.setFont(font())
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
        self.browse_btn.setFont(font())
        self.browse_btn.clicked.connect(self.pick_folder)
        settings_layout_lbl = QLabel("Save to:")
        settings_layout_lbl.setFont(font())
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
        bitrate_lbl.setFont(font())
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
        self.stats_label.setFont(font())
        self.stats_label.setAlignment(Qt.AlignCenter)
        prog_layout.addWidget(self.progress)
        prog_layout.addWidget(self.stats_label)
        p3_layout.addWidget(prog_frame)

        # Queue
        queue_lbl = QLabel("<b>Download Queue</b>")
        queue_lbl.setFont(font())
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
        font_title = font()
        font_title.setPointSize(24)
        font_title.setBold(True)
        self.success_title.setFont(font_title)
        self.success_title.setAlignment(Qt.AlignCenter)

        self.success_path = QLabel("Path...")
        self.success_path.setFont(font())
        self.success_path.setAlignment(Qt.AlignCenter)
        self.success_path.setStyleSheet("""
            color: #8ab4f8;
            margin-top: 15px;
            margin-bottom: 30px;
        """)

        p4_btns = QHBoxLayout()
        self.open_exported_btn = QPushButton("Open Folder")
        self.open_exported_btn.setFont(font())
        self.open_exported_btn.setMinimumHeight(50)

        self.new_download_btn = QPushButton("Start Another Download")
        self.new_download_btn.setFont(font())
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

        def reset_to_start(self):
            self.url_input.setText("")
            self.loading_label.setText("")
            self.stacked_widget.setCurrentIndex(0)

        def pick_folder(self):
            folder = QFileDialog.getExistingDirectory(self, "Select output folder", self.folder_input.text() or os.path.expanduser("~"))
            if folder:
                self.folder_input.setText(folder)

        def pick_cookies(self):
            f, _ = QFileDialog.getOpenFileName(self, "Select cookies file", "", "Text Files (*.txt);;All Files (*)")
            if f:
                self.cookies_input.setText(f)

        def _is_valid_url(self, url):
            return bool(re.match(r"^https?://", url))

        def preview_url(self):
            url = self.url_input.text().strip()
            if not self._is_valid_url(url):
                self.loading_label.setText("Invalid URL, please provide a valid link")
                self.update_log("Invalid URL.")
                return
            if self.meta_thread and self.meta_thread.isRunning():
                self.loading_label.setText("Metadata request already running...")
                return

            self.loading_label.setText("Fetching metadata, please wait...")
            self.preview_btn.setEnabled(False)
            self._set_status("Fetching metadata")

            t = DownloadThread({"url": url,}, mode="metadata")
            t.metadata_signal.connect(self.on_metadata)
            t.error_signal.connect(self.on_metadata_error)
            t.finished.connect(lambda: self._cleanup_meta_thread(t))
            t.start()
            self.meta_thread = t

        def _cleanup_meta_thread(self, t):
            if self.meta_thread is t:
                self.meta_thread = None
            t.deleteLater()

        def on_metadata_error(self, msg):
            self.loading_label.setText(f"{msg}")
            self.preview_btn.setEnabled(True)
            self._set_status("Error")
            self.update_log(f"{msg}")

        def on_metadata(self, info):
            self.loading_label.setText("")
            self.preview_btn.setEnabled(True)
            self.stacked_widget.setCurrentIndex(1)

            self.current_info = info or {}
            title = self.current_info.get("title", "")
            channel = self.current_info.get("channel", "")
            duration = self.current_info.get("duration_string", str(self.current_info.get("duration", "")))
            self.meta_label.setText(f"<b>Status:</b> Ready\n<br><br><b>Video details:</b>\nTitle: {title}\nChannel: {channel}\nDuration: {duration}")
            self.populate_formats(self.current_info)
            thumb = self.current_info.get("thumbnail", "")
            if thumb:
                self.net.get(QNetworkRequest(QUrl(thumb))).finished.connect(self._on_thumb_loaded)
            self.update_log(f"Metadata loaded")

        def on_thumb_loaded(self):
            reply = self.sender()
            data = reply.readAll()
            px = QPixmap()
            if px.loadFromData(data):
                self.thumb_label.setPixmap(px.scaled(self.thumb_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            reply.deleteLater()

        def build_task(self):
            return {
                "url": self.url_input.text().strip(),
                "folder": self.folder_input.text().strip() or os.path.expanduser("~"),
                "template": self.template_input.text().strip() or "%(title)s.%(ext)s",
                "format_id": self.format_box.currentData(),
                "convert_mode": self.convert_box.currentText(),
                "playlist": self.playlist_check.isChecked(),
                "max_items": self.max_items.value(),
                "mp3_bitrate": self.mp3_bitrate_box.currentText(),
                "cookies": self.cookies_input.text().strip(),
            }
