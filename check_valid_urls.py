from utils import is_valid_url, normalize_url
import requests

url1 = r"1 = https://youtu.be/KUrm-F8mXJQ"
url2 = r"2 = https://www.youtube.com/watch?v=KUrm-F8mXJQ&list=PLTDARY42LDV7WGmlzZtY-w9pemyPrKNUZ&index=4"

print('normalized1=', normalize_url(url1))
print('valid1=', is_valid_url(url1))
print('normalized2=', normalize_url(url2))
print('valid2=', is_valid_url(url2))

for url in (url1, url2):
    response = requests.post('http://127.0.0.1:5000/api/info', json={'url': url}, timeout=30)
    print('status=', response.status_code)
    print(response.text[:400])
