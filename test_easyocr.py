import sys
import ssl
import easyocr
import cv2

sys.stdout.reconfigure(encoding='utf-8')
ssl._create_default_https_context = ssl._create_unverified_context

reader = easyocr.Reader(['en'])
print("EasyOCR initialized")

# test extraction
result = reader.readtext(r'd:\C Data\Documents\GitHub\aI-article-generation\Ad materials\ENGLISH CREATIVE.jpeg')
for (bbox, text, prob) in result:
    print(bbox, text)
