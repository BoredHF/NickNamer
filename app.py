import mss
import cv2 as cv
import pytesseract
import re
import time
import pyautogui
import numpy as np
from PIL import Image

def preprocess_image(img):
    # Convert to grayscale
    gray = cv.cvtColor(img, cv.COLOR_BGR2GRAY)
    
    # Apply thresholding to get black and white image
    _, binary = cv.threshold(gray, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU)
    
    # Noise removal using median blur
    denoised = cv.medianBlur(binary, 3)
    
    # Dilation to make text thicker and clearer
    kernel = np.ones((2,2), np.uint8)
    dilated = cv.dilate(denoised, kernel, iterations=1)
    
    return dilated

def searchOG():
    pytesseract.pytesseract.tesseract_cmd = 'C:\Program Files\Tesseract-OCR\tesseract.exe'
    keepgoing = True
    
    # Configure tesseract parameters for better accuracy
    custom_config = r'--oem 3 --psm 7 -c tessedit_char_whitelist=abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.,'
    
    while(keepgoing):
        try:
            pyautogui.click("tryagain.png")
            pyautogui.click()
            time.sleep(1)
            
            with mss.mss() as screen:
                image = screen.grab({"top": 332, "left": 843, "width": 217, "height": 24})
                mss.tools.to_png(image.rgb, image.size, output="output.png")
            
            # Read and preprocess image
            img = cv.imread("output.png")
            if img is None:
                print("Failed to read image")
                continue
                
            # Apply HSV filtering
            hsv = cv.cvtColor(img, cv.COLOR_BGR2HSV)
            msk = cv.inRange(hsv, np.array([0, 0, 123]), np.array([179, 255, 255]))
            
            # Apply additional preprocessing
            processed = preprocess_image(img)
            
            # Combine both processed images for better results
            combined = cv.bitwise_and(processed, processed, mask=msk)
            
            # Scale up image for better OCR
            scaled = cv.resize(combined, None, fx=2, fy=2, interpolation=cv.INTER_CUBIC)
            
            # Get OCR text
            nick = pytesseract.image_to_string(scaled, config=custom_config).strip()
            print(f"Detected text: {nick}")
            
            if nick in ["name,", "name."]:
                pyautogui.click("hypixelerror.png")
                time.sleep(1.7)
            
            keepgoing = not(re.search(r'([a-z])\1{2,}', nick, re.IGNORECASE) is not None 
                          and sum(1 for letter in nick if letter.isupper()) == 1)
                
        except Exception as e:
            print(f"Error occurred: {str(e)}")
            time.sleep(1)
            continue
            
    pyautogui.click("Use.PNG")
    pyautogui.click()

if __name__ == "__main__":
    searchOG()