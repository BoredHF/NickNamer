import mss
import cv2 as cv
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
import easyocr

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
        # Initialize EasyOCR with basic settings
        self.reader = easyocr.Reader(
            ['en'], 
            gpu=True,
            model_storage_directory='./models',
            user_network_directory='./models'
        )
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
        # Convert to RGB first (EasyOCR prefers RGB)
        img_rgb = cv.cvtColor(img, cv.COLOR_BGR2RGB)
        
        # Scale up image significantly
        scaled = cv.resize(img_rgb, None, fx=5, fy=5, 
                         interpolation=cv.INTER_CUBIC)
        
        # Convert to grayscale after scaling
        gray = cv.cvtColor(scaled, cv.COLOR_RGB2GRAY)
        
        # Apply threshold to get pure black and white
        _, binary = cv.threshold(gray, 127, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
        
        # Add white padding around the image
        padded = cv.copyMakeBorder(binary, 20, 20, 20, 20, 
                                  cv.BORDER_CONSTANT, 
                                  value=[255, 255, 255])
        
        return padded


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

    def click_with_retry(self, image_name, retries=3):
        """Attempt to click an image with retries"""
        for i in range(retries):
            try:
                pyautogui.click(image_name)
                return True
            except Exception as e:
                self.update_text.emit(f"Click retry {i+1}/{retries}: {str(e)}")
                time.sleep(0.5)
        return False

    def run(self):
        while self.running:
            try:
                self.update_status.emit("Clicking try again...")
                if not self.click_with_retry("tryagain.png"):
                    self.update_status.emit("Failed to find button - retrying...")
                    continue
                
                with mss.mss() as screen:
                    # Adjusted capture area
                    image = screen.grab({
                        "top": 331,     # Moved up 1 pixel
                        "left": 842,    # Moved left 1 pixel
                        "width": 219,   # Slightly wider
                        "height": 26    # Slightly taller
                    })
                    mss.tools.to_png(image.rgb, image.size, output="output.png")
                
                img = cv.imread("output.png")
                if img is None:
                    self.update_status.emit("Failed to read image")
                    continue
                
                # Simple preprocessing
                processed = self.preprocess_image(img)
                
                # Save processed image for debugging
                cv.imwrite("processed.png", processed)
                
                # OCR with better confidence handling
                results = self.reader.readtext(
                    processed,
                    allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz,.',
                    batch_size=1,
                    min_size=20,  # Increased minimum text size
                    text_threshold=0.8,  # Higher confidence threshold
                    low_text=0.3,  # Lower text confidence threshold
                    link_threshold=0.3,  # Lower link confidence threshold
                    canvas_size=2560  # Larger canvas size
                )
                
                if not results:
                    self.update_text.emit("No text detected")
                    continue
                
                # Get the result with highest confidence
                result = max(results, key=lambda x: x[2])
                nick = result[1].strip()
                confidence = result[2]
                
                self.update_text.emit(f"Detected: {nick} (Confidence: {confidence:.2f})")
                
                if confidence < 0.8:  # Stricter confidence threshold
                    self.update_text.emit("Low confidence - skipping")
                    continue
                
                # Clean up the text
                nick = nick.rstrip('.,')
                
                # Additional validation
                if len(nick) < 3 or len(nick) > 16:  # Minecraft username length limits
                    continue
                    
                if not nick.replace('.', '').replace(',', '').isalpha():
                    self.update_text.emit("Contains non-letter characters - skipping")
                    continue
                
                if nick.lower() in ["name", "name,", "name."]:
                    self.update_status.emit("Found 'name', clicking error...")
                    if not self.click_with_retry("hypixelerror.png"):
                        continue
                    time.sleep(1.7)
                    continue
                
                # Pattern matching
                has_triple = re.search(r'([a-zA-Z])\1{2,}', nick) is not None
                capital_count = sum(1 for letter in nick if letter.isupper())
                only_letters = all(c.isalpha() for c in nick)
                
                self.update_text.emit(f"Analysis for '{nick}':")
                self.update_text.emit(f"Has triple letters: {has_triple}")
                self.update_text.emit(f"Capital letters: {capital_count}")
                self.update_text.emit(f"Only letters: {only_letters}")
                
                # Update statistics
                self.update_statistics(nick, has_triple, capital_count, only_letters)
                
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

    def stop(self):
        """Stop the worker thread"""
        self.running = False
        self.cleanup()

    def cleanup(self):
        """Clean up resources"""
        if hasattr(self, 'reader'):
            del self.reader
        # Remove temporary files
        if os.path.exists("output.png"):
            try:
                os.remove("output.png")
            except:
                pass
        if os.path.exists("processed.png"):
            try:
                os.remove("processed.png")
            except:
                pass

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
        if hasattr(self, 'worker'):
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