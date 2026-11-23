import pytesseract

# Point to your actual Tesseract executable location
pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Users\FL_LPT-370\AppData\Local\Tesseract-OCR\tesseract.exe"
)

# Check Tesseract version
try:
    version = pytesseract.get_tesseract_version()
    print("Tesseract connected successfully!")
    print("Version:", version)
except Exception as e:
    print("Error connecting to Tesseract:", e)