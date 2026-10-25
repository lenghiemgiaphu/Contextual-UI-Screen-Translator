"""Bảng màu (Catppuccin Mocha) và stylesheet dùng chung."""
BASE = "#1E1E2E"
MANTLE = "#181825"
SURFACE = "#313244"
SURFACE1 = "#45475A"
SURFACE2 = "#585B70"
OVERLAY = "#6C7086"
TEXT = "#CDD6F4"
SUBTEXT = "#A6ADC8"
BLUE = "#89B4FA"
GREEN = "#A6E3A1"
YELLOW = "#F9E2AF"
RED = "#F38BA8"
SKY = "#89DCEB"
CRUST = "#11111B"

DIALOG_STYLE = f"""
QDialog {{ background: {BASE}; color: {TEXT}; }}
QLabel {{ color: {TEXT}; }}
QLabel#Hint {{ color: {SUBTEXT}; font-size: 9pt; }}
QLineEdit, QSpinBox, QComboBox {{
    background: {SURFACE}; color: {TEXT}; border: 1px solid {SURFACE1};
    border-radius: 5px; padding: 4px 8px; min-height: 22px;
}}
QComboBox QAbstractItemView {{ background: {SURFACE}; color: {TEXT}; selection-background-color: {SURFACE1}; }}
QPushButton {{ background: {SURFACE1}; color: {TEXT}; border: none; border-radius: 5px; padding: 6px 14px; }}
QPushButton:hover {{ background: {SURFACE2}; }}
QPushButton#Primary {{ background: {BLUE}; color: {CRUST}; font-weight: bold; }}
QPushButton#Danger {{ background: {RED}; color: {CRUST}; font-weight: bold; }}
QCheckBox {{ color: {TEXT}; spacing: 8px; }}
QGroupBox {{ color: {BLUE}; border: 1px solid {SURFACE1}; border-radius: 6px; margin-top: 10px; padding: 10px 8px 6px 8px; font-weight: bold; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; }}
QTableWidget {{
    background: {BASE}; color: {TEXT}; gridline-color: {SURFACE1};
    border: 1px solid {SURFACE1}; selection-background-color: {SURFACE1}; alternate-background-color: #252536;
}}
QHeaderView::section {{ background: {SURFACE}; color: {BLUE}; border: none; padding: 6px; font-weight: bold; }}
QSlider::groove:horizontal {{ background: {SURFACE1}; height: 4px; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {BLUE}; width: 14px; margin: -6px 0; border-radius: 7px; }}
"""

OVERLAY_STYLE = f"""
QFrame#MainContainer {{ background: {BASE}; border: 2px solid {BLUE}; border-radius: 10px; }}
QFrame#Row {{ background: {SURFACE}; border: 1px solid {SURFACE1}; border-radius: 6px; }}
QFrame#Row QLabel {{ border: none; background: transparent; }}
QLabel {{ color: {TEXT}; }}
QLabel#Status {{ color: {SUBTEXT}; font-size: 8pt; }}
QLabel#Empty {{ color: {SUBTEXT}; padding: 14px; }}
QComboBox {{
    background: {SURFACE}; color: {BLUE}; border: 1px solid {SURFACE1};
    border-radius: 5px; padding: 3px 8px; font-weight: bold;
}}
QComboBox QAbstractItemView {{ background: {SURFACE}; color: {TEXT}; selection-background-color: {SURFACE1}; }}
QPushButton {{ background: {SURFACE1}; color: {TEXT}; border: none; border-radius: 4px; padding: 2px 8px; }}
QPushButton:hover {{ background: {SURFACE2}; }}
QPushButton:checked {{ background: {BLUE}; color: {CRUST}; }}
QPushButton#CloseBtn {{ background: {RED}; color: {CRUST}; font-weight: bold; }}
QScrollArea {{ border: none; background: transparent; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: {SURFACE2}; border-radius: 4px; min-height: 20px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""
