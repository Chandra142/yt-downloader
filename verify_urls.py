from utils import is_valid_url

urls = [
    '1 = https://youtu.be/KUrm-F8mXJQ',
    '2 = https://www.youtube.com/watch?v=KUrm-F8mXJQ&list=PLTDARY42LDV7WGmlzZtY-w9pemyPrKNUZ&index=4',
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://example.com/video',
]

for url in urls:
    print(f'{url} -> {is_valid_url(url)}')
