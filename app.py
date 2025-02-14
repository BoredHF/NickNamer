import mss
import cv2 as cv
import re
import time
import pyautogui
import numpy as np
from PIL import Image
import easyocr
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
    update_stats = pyqtSignal(dict)  # New signal for stats

    def __init__(self, delay=1.0):
        super().__init__()
        self.running = True
        self.delay = delay
        # Initialize EasyOCR reader
        self.reader = easyocr.Reader(['en'], gpu=False)
        # Initialize statistics
        self.stats = {
            'total_attempts': 0,
            'names_checked': 0,
            'triple_letters_found': 0,
            'single_capital_found': 0,
            'valid_names_found': 0,
            'errors': 0,
            'start_time': time.time()
        }

    def preprocess_image(self, img):
        # Create multiple preprocessing versions
        preprocessed_images = []
        
        # Version 1: High contrast with adaptive thresholding
        gray1 = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        # Increase image size before processing
        gray1 = cv.resize(gray1, None, fx=4, fy=4, interpolation=cv.INTER_CUBIC)
        # Apply bilateral filter to reduce noise while keeping edges sharp
        denoised1 = cv.bilateralFilter(gray1, 9, 75, 75)
        # Adaptive threshold
        binary1 = cv.adaptiveThreshold(denoised1, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C, 
                                     cv.THRESH_BINARY, 11, 2)
        preprocessed_images.append(binary1)
        
        # Version 2: CLAHE with Otsu's thresholding
        gray2 = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        gray2 = cv.resize(gray2, None, fx=4, fy=4, interpolation=cv.INTER_CUBIC)
        # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray2)
        # Gaussian blur to reduce noise
        blurred = cv.GaussianBlur(enhanced, (5,5), 0)
        # Otsu's thresholding
        _, binary2 = cv.threshold(blurred, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
        preprocessed_images.append(binary2)
        
        # Version 3: Edge enhancement
        gray3 = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
        gray3 = cv.resize(gray3, None, fx=4, fy=4, interpolation=cv.INTER_CUBIC)
        # Sharpen image
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv.filter2D(gray3, -1, kernel)
        # Otsu's thresholding
        _, binary3 = cv.threshold(sharpened, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
        preprocessed_images.append(binary3)
        
        return preprocessed_images

    def validate_text(self, text):
        """Validate and clean the detected text"""
        # Remove common OCR mistakes
        replacements = {
            '0': 'O',
            '1': 'l',
            '8': 'B',
            '5': 'S',
            '2': 'Z',
            '6': 'b',
            '9': 'g'
        }
        
        # Clean the text
        cleaned = text.strip()
        # Replace commonly confused characters
        for num, letter in replacements.items():
            cleaned = cleaned.replace(num, letter)
        
        # Remove any remaining non-letter characters except comma and period
        cleaned = ''.join(c for c in cleaned if c.isalpha() or c in '.,')
        
        return cleaned

    def update_statistics(self, nick, has_triple, capital_count, only_letters):
        self.stats['total_attempts'] += 1
        if nick:
            self.stats['names_checked'] += 1
        if has_triple:
            self.stats['triple_letters_found'] += 1
        if capital_count == 1:
            self.stats['single_capital_found'] += 1
        if has_triple and capital_count == 1 and only_letters:
            self.stats['valid_names_found'] += 1
            
        # Calculate runtime
        runtime = time.time() - self.stats['start_time']
        self.stats['runtime'] = f"{int(runtime // 3600):02d}:{int((runtime % 3600) // 60):02d}:{int(runtime % 60):02d}"
        
        # Calculate rates
        if runtime > 0:
            self.stats['names_per_minute'] = round(self.stats['names_checked'] / (runtime / 60), 2)
            
        # Calculate success rate
        if self.stats['names_checked'] > 0:
            self.stats['success_rate'] = round((self.stats['valid_names_found'] / self.stats['names_checked']) * 100, 2)
        else:
            self.stats['success_rate'] = 0.0
            
        self.update_stats.emit(self.stats)

    def run(self):
        while self.running:
            try:
                self.update_status.emit("Clicking try again...")
                pyautogui.click("tryagain.png")
                pyautogui.click()
                time.sleep(self.delay)
                
                with mss.mss() as screen:
                    # Increased capture area slightly
                    image = screen.grab({"top": 326, "left": 838, "width": 229, "height": 36})
                    mss.tools.to_png(image.rgb, image.size, output="output.png")
                
                img = cv.imread("output.png")
                if img is None:
                    self.update_status.emit("Failed to read image")
                    continue
                
                # Get all preprocessed versions
                processed_images = self.preprocess_image(img)
                
                # Try OCR with different preprocessed images
                all_attempts = []
                for processed in processed_images:
                    # EasyOCR detection
                    results = self.reader.readtext(processed)
                    for result in results:
                        text = result[1].strip()
                        if text:
                            # Clean and validate the text
                            cleaned_text = self.validate_text(text)
                            if cleaned_text:
                                all_attempts.append(cleaned_text)
                
                # Debug output
                self.update_text.emit("OCR attempts:")
                for i, attempt in enumerate(all_attempts):
                    self.update_text.emit(f"Attempt {i+1}: {attempt}")
                
                if not all_attempts:
                    continue
                
                # Choose the best result - prefer results with more letters
                nick = max(all_attempts, 
                         key=lambda x: sum(c.isalpha() for c in x), 
                         default="")
                
                if not nick:
                    continue
                
                self.update_text.emit(f"Selected: {nick}")
                
                if nick.lower() in ["name,", "name.", "name"]:
                    self.update_status.emit("Found 'name', clicking error...")
                    pyautogui.click("hypixelerror.png")
                    time.sleep(1.7)
                    continue
                
                # Updated pattern matching with better debugging
                # Check for exactly one capital letter
                capital_count = sum(1 for letter in nick if letter.isupper())
                
                # Check for three or more of the same letter in a row (case insensitive)
                has_triple = re.search(r'([a-zA-Z])\1{2,}', nick) is not None
                
                # Check that the name contains only letters (no numbers or special chars)
                only_letters = all(c.isalpha() for c in nick.replace(',', '').replace('.', ''))
                
                self.update_text.emit(f"Analysis for '{nick}':")
                self.update_text.emit(f"Has triple letters: {has_triple}")
                self.update_text.emit(f"Capital letters: {capital_count}")
                self.update_text.emit(f"Only letters: {only_letters}")
                
                # Update statistics before pattern matching
                self.update_statistics(nick, has_triple, capital_count, only_letters)
                
                # All conditions must be met:
                # 1. Exactly one capital letter
                # 2. Has triple letters
                # 3. Contains only letters (no numbers)
                if has_triple and capital_count == 1 and only_letters:
                    self.update_status.emit("Valid name found! Clicking Use...")
                    pyautogui.click("Use.PNG")
                    pyautogui.click()
                    break
                
                self.update_progress.emit(50)
                
            except Exception as e:
                self.stats['errors'] += 1
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

        # Create stats display
        self.stats_container = QWidget()
        stats_layout = QVBoxLayout(self.stats_container)
        
        self.stats_labels = {
            'runtime': QLabel("Runtime: 00:00:00"),
            'total_attempts': QLabel("Total Attempts: 0"),
            'names_checked': QLabel("Names Checked: 0"),
            'names_per_minute': QLabel("Names per Minute: 0.00"),
            'triple_letters_found': QLabel("Triple Letters Found: 0"),
            'single_capital_found': QLabel("Single Capital Found: 0"),
            'valid_names_found': QLabel("Valid Names Found: 0"),
            'success_rate': QLabel("Success Rate: 0.00%"),
            'errors': QLabel("Errors: 0")
        }
        
        # Add stats labels to layout
        for label in self.stats_labels.values():
            label.setStyleSheet("""
                background-color: #1e1e1e;
                padding: 5px;
                border-radius: 3px;
                margin: 2px;
            """)
            stats_layout.addWidget(label)

        # Add widgets to layout
        layout.addWidget(self.stats_container)
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
        self.worker.update_stats.connect(self.update_stats)  # Connect stats signal
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

    def update_stats(self, stats):
        self.stats_labels['runtime'].setText(f"Runtime: {stats['runtime']}")
        self.stats_labels['total_attempts'].setText(f"Total Attempts: {stats['total_attempts']}")
        self.stats_labels['names_checked'].setText(f"Names Checked: {stats['names_checked']}")
        self.stats_labels['names_per_minute'].setText(f"Names per Minute: {stats['names_per_minute']}")
        self.stats_labels['triple_letters_found'].setText(f"Triple Letters Found: {stats['triple_letters_found']}")
        self.stats_labels['single_capital_found'].setText(f"Single Capital Found: {stats['single_capital_found']}")
        self.stats_labels['valid_names_found'].setText(f"Valid Names Found: {stats['valid_names_found']}")
        self.stats_labels['success_rate'].setText(f"Success Rate: {stats['success_rate']}%")
        self.stats_labels['errors'].setText(f"Errors: {stats['errors']}")

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