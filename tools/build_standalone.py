"""Build a single portable HTML file using the Python standard library."""
from base64 import b64encode
from pathlib import Path
import mimetypes
import re

root = Path(__file__).resolve().parents[1]
page = (root / 'index.html').read_text(encoding='utf-8')
css = (root / 'style.css').read_text(encoding='utf-8')
page = page.replace('<link rel="stylesheet" href="style.css">', f'<style>\n{css}\n</style>')
script = (root / 'script.js').read_text(encoding='utf-8')
page = page.replace('<script src="script.js" defer></script>', '')
page = page.replace('</body>', f'<script>\n{script}\n</script>\n</body>')
for asset in sorted(set(re.findall(r'(?:src|href|data-detail)="(assets/[^\"]+)"', page))):
    encoded = b64encode((root / asset).read_bytes()).decode('ascii')
    mime = mimetypes.guess_type(asset)[0] or 'application/octet-stream'
    page = page.replace(asset, f'data:{mime};base64,{encoded}')
(root / 'site.html').write_text(page, encoding='utf-8')
print('site.html')
