import os, re, sys, time, shutil, yt_dlp, platform

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QUrl, QByteArray

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
            return f"FFmpeg error: {err}"
        if "network" in s or "timed out" in s or "connection" in s or "dns" in s:
            return f"Network error: {err}"
        if "login" in s or "sign in" in s or "private" in s or "members" in s or "forbidden" in s:
            return f"Restricted content: {err}"
        if "javascript" in s or "runtime" in s:
            return f"Javascript runtime error: {err}"
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

            if ffmpeg_location and os.path.isdir(ffmpeg_location):
                current_path = os.environ.get("PATH", "")
                if ffmpeg_location not in current_path:
                    os.environ["PATH"] = ffmpeg_location + os.pathsep + current_path

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
            convert_mode = self.task.get("convert_mode", "Extract Audio as MP3 (Default)")
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
                if convert_mode == "Convert video to MP4":
                    ydl_opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
                elif convert_mode == "Extract Audio as MP3 (Default)":
                    ydl_opts["format"] = "bestaudio/best"
                    post.append({
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": self.task.get("mp3_bitrate", "192")
                    })
                else:
                    ydl_opts["format"] = "bestvideo+bestaudio/best"

            if convert_mode == "Convert video to MP4":
                post.append({"key": "FFmpegVideoConvertor", "preferedformat": "mp4"})
                ydl_opts.setdefault("postprocessor_args", {})["FFmpegVideoConvertor"] = ["-c:a", "aac"]
            elif convert_mode == "Convert video to MKV":
                post.append({"key": "FFmpegVideoConvertor", "preferedformat": "mkv"})
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