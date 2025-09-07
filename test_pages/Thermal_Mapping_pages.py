from typing import Callable

from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout

class ThermalMappingPage(QWidget):
    def __init__(self, db, get_pid: Callable[[], int]):
        super().__init__()
        self.db = db
        self.get_pid = get_pid
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Thermal Mapping Tests"))
        self.setLayout(layout)
