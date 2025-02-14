import mss
import cv2 as cv
import pytesseract
import re
import time
import pyautogui
import numpy as np
from PIL import Image
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QLabel, 
                            QVBoxLayout, QWidget, QTextEdit, QProgressBar,
                            QSlider, QHBoxLayout)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QPixmap, QImage
import sys
import os

class OCRWorker(QThread):
    update_image = pyqtSignal(QImage)
    update_text = pyqtSignal(str)
    update_status = pyqtSignal(str)
    update_progress = pyqtSignal(int)

    def __init__(self, delay=1.0):
        super().__init__()
        self.running = True
        self.delay = delay

    def set_delay(self, delay):
        self.delay = delay

    def stop(self):
        self.running = False

    def preprocess_image(self, img):
        # Convert to grayscale
        gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        
        # Increase contrast
        clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        gray = clahe.apply(gray)
        
        # Apply adaptive thresholding instead of simple threshold
        binary = cv.adaptiveThreshold(gray, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                    cv.THRESH_BINARY, 11, 2)
        
        # Remove noise
        denoised = cv.fastNlMeansDenoising(binary)
        
        # Scale up image before further processing
        scaled = cv.resize(denoised, None, fx=2, fy=2, interpolation=cv.INTER_CUBIC)
        
        # Dilate to make text clearer
        kernel = np.ones((2,2), np.uint8)
        dilated = cv.dilate(scaled, kernel, iterations=1)
        
        return dilated

    def run(self):
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
        # Update config to include numbers and underscore
        custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_,.'
        
        while self.running:
            try:
                self.update_status.emit("Clicking try again...")
                pyautogui.click("tryagain.png")
                pyautogui.click()
                time.sleep(self.delay)
                
                with mss.mss() as screen:
                    # Capture a slightly larger area
                    image = screen.grab({"top": 330, "left": 841, "width": 221, "height": 28})
                    mss.tools.to_png(image.rgb, image.size, output="output.png")
                
                img = cv.imread("output.png")
                if img is None:
                    self.update_status.emit("Failed to read image")
                    continue
                
                # Enhanced image processing
                processed = self.preprocess_image(img)
                
                # Apply multiple processing methods and combine results
                hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)
                msk = cv.inRange(hsv, np.array([0, 0, 123]), np.array([179, 255, 255]))
                msk = cv.resize(msk, (processed.shape[1], processed.shape[0]))
                
                combined = cv.bitwise_and(processed, processed, mask=msk)
                
                # Convert to QImage for display
                h, w = combined.shape
                q_img = QImage(combined.data, w, h, w, QImage.Format.Format_Grayscale8)
                self.update_image.emit(q_img)
                
                # Multiple OCR attempts with different preprocessing
                nick_attempts = [
                    pytesseract.image_to_string(combined, config=custom_config).strip(),
                    pytesseract.image_to_string(processed, config=custom_config).strip(),
                    pytesseract.image_to_string(msk, config=custom_config).strip()
                ]
                
                # Use the most likely result (non-empty and contains valid characters)
                nick = next((n for n in nick_attempts if n and any(c.isalnum() or c == '_' for c in n)), nick_attempts[0])
                
                self.update_text.emit(f"Detected: {nick}")
                
                if nick in ["name,", "name."]:
                    self.update_status.emit("Found 'name', clicking error...")
                    pyautogui.click("hypixelerror.png")
                    time.sleep(1.7)
                    continue
                
                # Updated pattern matching
                has_triple = re.search(r'([a-z])\1{2,}', nick, re.IGNORECASE) is not None
                capital_count = sum(1 for letter in nick if letter.isupper())
                valid_chars = all(c.isalnum() or c == '_' for c in nick.replace(',', '').replace('.', ''))
                
                # Print debug info
                self.update_text.emit(f"Triple letters: {has_triple}")
                self.update_text.emit(f"Capital count: {capital_count}")
                
                # Only proceed if exactly one capital and has triple letters
                if has_triple and capital_count == 1 and valid_chars:
                    # Double check the pattern
                    if re.search(r'([a-zA-Z])\1{2,}', nick) is not None:
                        self.update_status.emit("Valid name found! Clicking Use...")
                        pyautogui.click("Use.PNG")
                        pyautogui.click()
                        break
                    else:
                        self.update_text.emit("Triple letter pattern not confirmed")
                
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

        # Create delay control
        delay_container = QWidget()
        delay_layout = QHBoxLayout(delay_container)
        
        self.delay_label = QLabel("Delay (seconds): 1.0")
        self.delay_slider = QSlider(Qt.Orientation.Horizontal)
        self.delay_slider.setMinimum(5)
        self.delay_slider.setMaximum(30)
        self.delay_slider.setValue(10)  # Default 1.0 second (10 * 0.1)
        self.delay_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.delay_slider.setTickInterval(5)
        self.delay_slider.valueChanged.connect(self.update_delay_label)
        
        delay_layout.addWidget(self.delay_label)
        delay_layout.addWidget(self.delay_slider)

        # Create other GUI elements
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
        layout.addWidget(delay_container)
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
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 8px;
                background: #363636;
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #0d47a1;
                border: 1px solid #0d47a1;
                width: 18px;
                margin: -2px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: #1565c0;
            }
        """)

    def update_delay_label(self):
        delay = self.delay_slider.value() / 10.0
        self.delay_label.setText(f"Delay (seconds): {delay:.1f}")
        if hasattr(self, 'worker'):
            self.worker.set_delay(delay)

    def start_ocr(self):
        delay = self.delay_slider.value() / 10.0
        self.worker = OCRWorker(delay=delay)
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
    # Set DPI awareness
    if os.name == 'nt':  # Windows only
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass  # Ignore if it fails
            
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())