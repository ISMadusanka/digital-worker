import sys
import time
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
    QLineEdit, QPushButton, QTextEdit, QLabel, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QColor

from core.worker import DigitalWorker
from services.screenshot import ScreenshotService
from actions.executor import ActionExecutor

class WorkerThread(QThread):
    step_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(str)
    
    def __init__(self, goal: str):
        super().__init__()
        self.goal = goal
        self.worker = None
        self._stop_requested = False

    def run(self):
        try:
            # Build the worker HERE so its heavy startup (model client) and the
            # UI Automation / COM initialization happen on this worker thread —
            # not on the GUI thread (no launch freeze) and on the same thread
            # that later drives UIA.
            self.worker = DigitalWorker(on_step_callback=self.step_signal.emit)
            if self._stop_requested:
                self.worker.stop_requested = True
            result = self.worker.execute_goal(self.goal)
            self.finished_signal.emit(result)
        except Exception as e:
            self.finished_signal.emit(f"Error: {str(e)}")

    def stop(self):
        self._stop_requested = True
        if self.worker is not None:
            self.worker.stop_requested = True

class DigitalWorkerUI(QWidget):
    hide_signal = pyqtSignal()
    show_signal = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.worker_thread = None
        self._pending_quit = False
        self.init_ui()
        self.setup_hooks()
        
    def setup_hooks(self):
        # Use BlockingQueuedConnection to ensure the UI is fully hidden before the worker thread proceeds
        self.hide_signal.connect(self._do_hide, Qt.ConnectionType.BlockingQueuedConnection)
        self.show_signal.connect(self._do_show, Qt.ConnectionType.BlockingQueuedConnection)

        ScreenshotService.on_before_screenshot = self.hide_signal.emit
        ScreenshotService.on_after_screenshot = self.show_signal.emit
        ActionExecutor.on_before_action = self.hide_signal.emit
        ActionExecutor.on_after_action = self.show_signal.emit
        
    def _do_hide(self):
        self.hide()
        QApplication.processEvents()
        
    def _do_show(self):
        self.show()
        QApplication.processEvents()
        
    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Main layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Container frame
        self.container = QFrame(self)
        self.container.setObjectName("Container")
        self.container.setStyleSheet("""
            QFrame#Container {
                background-color: rgba(30, 30, 30, 240);
                border-radius: 15px;
                border: 1px solid #555;
            }
        """)
        self.container_layout = QVBoxLayout(self.container)
        
        # --- Expanded View ---
        self.expanded_widget = QWidget()
        self.expanded_layout = QVBoxLayout(self.expanded_widget)
        
        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        self.chat_history.setStyleSheet("""
            QTextEdit {
                background-color: transparent; 
                color: #ECECEC; 
                border: none; 
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }
        """)
        
        self.input_layout = QHBoxLayout()
        self.goal_input = QLineEdit()
        self.goal_input.setPlaceholderText("What would you like me to do?")
        self.goal_input.setStyleSheet("""
            QLineEdit {
                background-color: #252526;
                color: white;
                border: 1px solid #3E3E42;
                border-radius: 10px;
                padding: 10px;
                font-family: 'Segoe UI', sans-serif;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1px solid #007ACC;
            }
        """)
        self.goal_input.returnPressed.connect(self.start_worker)
        
        self.run_btn = QPushButton("Run")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #007ACC;
                color: white;
                border-radius: 10px;
                padding: 10px 20px;
                font-family: 'Segoe UI', sans-serif;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover { background-color: #0098FF; }
            QPushButton:pressed { background-color: #005A9E; }
        """)
        self.run_btn.clicked.connect(self.start_worker)
        
        self.input_layout.addWidget(self.goal_input)
        self.input_layout.addWidget(self.run_btn)
        
        self.close_btn = QPushButton("Close")
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; 
                color: #888; 
                font-family: 'Segoe UI', sans-serif;
                font-size: 12px; 
                border: none;
            }
            QPushButton:hover { color: white; }
        """)
        self.close_btn.clicked.connect(self.shutdown)
        
        self.expanded_layout.addWidget(self.chat_history)
        self.expanded_layout.addLayout(self.input_layout)
        self.expanded_layout.addWidget(self.close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        
        # --- Collapsed (Pill) View ---
        self.collapsed_widget = QWidget()
        self.collapsed_layout = QHBoxLayout(self.collapsed_widget)
        self.collapsed_layout.setContentsMargins(15, 5, 10, 5)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #ECECEC; 
                font-family: 'Segoe UI', sans-serif;
                font-size: 14px; 
                font-weight: 500;
            }
        """)
        
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setStyleSheet("""
            QPushButton {
                background-color: #E81123;
                color: white;
                border-radius: 8px;
                padding: 6px 15px;
                font-family: 'Segoe UI', sans-serif;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #F1707A; }
            QPushButton:pressed { background-color: #A80000; }
        """)
        self.stop_btn.clicked.connect(self.stop_worker)
        
        self.collapsed_layout.addWidget(self.status_label, stretch=1)
        self.collapsed_layout.addWidget(self.stop_btn)
        
        # Add to container
        self.container_layout.addWidget(self.expanded_widget)
        self.container_layout.addWidget(self.collapsed_widget)
        self.layout.addWidget(self.container)
        
        self.set_expanded_mode()
        
        # Dragging variables
        self._drag_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()
        
    def set_expanded_mode(self):
        self.collapsed_widget.hide()
        self.expanded_widget.show()
        self.resize(450, 350)
        # Position top right
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 480, 40)
        
    def set_collapsed_mode(self):
        self.expanded_widget.hide()
        self.collapsed_widget.show()
        self.resize(320, 60)
        # Position top center
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - 320) // 2, 40)
        
    def start_worker(self):
        goal = self.goal_input.text().strip()
        if not goal:
            return
            
        self.chat_history.append(f"<b style='color: #4DB8FF'>You:</b> {goal}<br>")
        self.goal_input.clear()
        
        self.status_label.setText("Starting...")
        self.set_collapsed_mode()
        
        self.worker_thread = WorkerThread(goal)
        self.worker_thread.step_signal.connect(self.on_worker_step)
        self.worker_thread.finished_signal.connect(self.on_worker_finished)
        self.worker_thread.start()
        
    def stop_worker(self):
        if self.worker_thread:
            self.status_label.setText("Stopping...")
            self.worker_thread.stop()
            self.chat_history.append(f"<b style='color: #F44336'>System:</b> Stop requested.<br>")
            
    def on_worker_step(self, message: str):
        # Truncate long messages for the pill
        short_msg = message if len(message) < 40 else message[:37] + "..."
        self.status_label.setText(short_msg)
        self.chat_history.append(f"<b style='color: #4CAF50'>Agent:</b> {message}<br>")
        
    def on_worker_finished(self, result: str):
        self.chat_history.append(f"<b>Result:</b> {result}<br><br>")
        if self._pending_quit:
            QApplication.quit()
            return
        self.set_expanded_mode()

    def shutdown(self):
        """Stop the worker (if running) and quit cleanly.

        We do NOT block the GUI thread waiting for the worker, because the worker
        hides/shows this window via a blocking queued signal — blocking here would
        deadlock. Instead we request a stop and quit once the worker reports back.
        """
        if self.worker_thread and self.worker_thread.isRunning():
            self._pending_quit = True
            self.status_label.setText("Stopping…")
            self.worker_thread.stop()
        else:
            QApplication.quit()

    def closeEvent(self, event):
        # Alt+F4 / window close: stop the worker first, then let it quit.
        if self.worker_thread and self.worker_thread.isRunning():
            self.shutdown()
            event.ignore()
        else:
            event.accept()
            QApplication.quit()

def _enable_dpi_awareness():
    """Make the process per-monitor DPI aware BEFORE Qt starts.

    This keeps screenshots, UI Automation bounding boxes, and PyAutoGUI click
    coordinates all in the same (physical-pixel) space on scaled displays, and
    silences Qt's DPI-context warning.
    """
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        pass


def main():
    _enable_dpi_awareness()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    ui = DigitalWorkerUI()
    ui.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
