from app import App, font
import sys

from PySide6.QtCore import Qt, QThread, Signal, QSettings, QUrl, QByteArray
from PySide6.QtGui import QDesktopServices, QPixmap, QAction, QFont, QFontDatabase, QIcon
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QTextEdit, QLabel, QComboBox, QFileDialog,
    QCheckBox, QSpinBox, QProgressBar, QTableWidget, QTableWidgetItem,
    QMessageBox, QHeaderView, QAbstractItemView, QMenu, QStackedWidget, QMainWindow
)

app = QApplication(sys.argv)
app.setWindowIcon(QIcon("icon.ico"))
cached_app_font = font()
font_family = cached_app_font.family()
app.setFont(cached_app_font)
app.setStyleSheet(f"""
    QWidget {{
        background-color: #202124;
        color: #f1f3f4;
        font-family: {font_family};
        font-size: 10pt;
    }}
    #Card {{
        background-color: #2b2b2b;
        border-radius: 8px;
        border: 1px solid #3c3c3c;
        font-family: {font_family};
    }}
    QLineEdit, QTextEdit , QComboBox, QSpinBox , QTableWidget {{
        background-color: #303134;
        color: #e8eaed;
        border: 1px solid #5f6368; 
        border-radius: 5px; 
        padding: 5px 12px; 
        font-family: {font_family};
        font-weight: bold;
    }}
    QPushButton {{
        background-color: #3c4043;
        color: #f1f3f4;
        border: 1px solid #5f6368;
        border-radius: 6px;
        padding: 5px 15px;
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
        border-radius: 6px;
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
        font-family: {font_family}; 
    }}
    QHeaderView::section {{ 
        background-color: #3c4043; 
        padding: 4px; 
        border: 1px solid #444; 
        font-weight: bold; 
        font-family: {font_family};
    }}
    QTableWidget::item:selected {{ 
        background-color: #4169E1; 
        color: white; 
        font-family: {font_family};
    }}
""")

window = App()
window.show()
sys.exit(app.exec())