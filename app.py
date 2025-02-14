import mss
import cv2 as cv
import pytesseract
import re
import time
import pyautogui
import numpy as np
from PIL import Image
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QLabel, 
                            QVBoxLayout, QWidget, QTextEdit, QProgressBar)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QPixmap, QImage
import sys

class OCRWorker(QThread):
    update_image = pyqtSignal(QImage)
    update_text = pyqtSignal(str)
    update_status = pyqtSignal(str)
    update_progress = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.running = True

    def stop(self):
        self.running = False

    def preprocess_image(self, img):
        gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        _, binary = cv.threshold(gray, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
        denoised = cv.medianBlur(binary, 3)
        kernel = np.ones((2,2), np.uint8)
        dilated = cv.dilate(denoised, kernel, iterations=1)
        return dilated

    def run(self):
        pytesseract.pytesseract.tesseract_cmd = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
        custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.,'
        
        while self.running:
            try:
                self.update_status.emit("Clicking try again...")
                pyautogui.click("tryagain.png")
                pyautogui.click()
                time.sleep(1)
                
                with mss.mss() as screen:
                    image = screen.grab({"top": 332, "left": 843, "width": 217, "height": 24})
                    mss.tools.to_png(image.rgb, image.size, output="output.png")
                
                img = cv.imread("output.png")
                if img is None:
                    self.update_status.emit("Failed to read image")
                    continue
                
                # Process image and update GUI
                hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)
                msk = cv.inRange(hsv, np.array([0, 0, 123]), np.array([179, 255, 255]))
                processed = self.preprocess_image(img)
                combined = cv.bitwise_and(processed, processed, mask=msk)
                scaled = cv.resize(combined, None, fx=2, fy=2, interpolation=cv.INTER_CUBIC)
                
                # Convert to QImage for display
                h, w = scaled.shape
                q_img = QImage(scaled.data, w, h, w, QImage.Format.Format_Grayscale8)
                self.update_image.emit(q_img)
                
                # OCR
                nick = pytesseract.image_to_string(scaled, config=custom_config).strip()
                self.update_text.emit(f"Detected: {nick}")
                
                if nick in ["name,", "name."]:
                    self.update_status.emit("Found 'name', clicking error...")
                    pyautogui.click("hypixelerror.png")
                    time.sleep(1.7)
                
                if (re.search(r'([a-z])\1{2,}', nick, re.IGNORECASE) is not None 
                    and sum(1 for letter in nick if letter.isupper()) == 1):
                    self.update_status.emit("Valid name found! Clicking Use...")
                    pyautogui.click("Use.PNG")
                    pyautogui.click()
                    break
                
                self.update_progress.emit(50)
                
            except Exception as e:
                self.update_status.emit(f"Error: {str(e)}")
                time.sleep(1)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Name Checker OCR")
        self.setMinimumSize(500, 600)

        # Create main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Create GUI elements
        self.start_button = QPushButton("Start")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setEnabled(False)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_output = QTextEdit()
        self.text_output.setReadOnly(True)
        self.status_label = QLabel("Status: Ready")
        self.progress_bar = QProgressBar()

        # Add widgets to layout
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.image_label)
        layout.addWidget(self.text_output)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        # Connect buttons
        self.start_button.clicked.connect(self.start_ocr)
        self.stop_button.clicked.connect(self.stop_ocr)

        # Style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
            }
            QLabel, QTextEdit {
                color: #ffffff;
                background-color: #363636;
                border-radius: 5px;
                padding: 5px;
            }
            QPushButton {
                background-color: #0d47a1;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1565c0;
            }
            QPushButton:disabled {
                background-color: #666666;
            }
            QProgressBar {
                border: 2px solid #666666;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #0d47a1;
            }
        """)

    def start_ocr(self):
        self.worker = OCRWorker()
        self.worker.update_image.connect(self.update_image)
        self.worker.update_text.connect(self.update_text)
        self.worker.update_status.connect(self.update_status)
        self.worker.update_progress.connect(self.progress_bar.setValue)
        self.worker.start()
        
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

    def stop_ocr(self):
        self.worker.stop()
        self.worker.wait()
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.update_status("Stopped")

    def update_image(self, q_img):
        pixmap = QPixmap.fromImage(q_img)
        self.image_label.setPixmap(pixmap.scaled(
            self.image_label.width(), 
            self.image_label.height(),
            Qt.AspectRatioMode.KeepAspectRatio
        ))

    def update_text(self, text):
        self.text_output.append(text)

    def update_status(self, status):
        self.status_label.setText(f"Status: {status}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())