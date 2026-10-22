"""Build a single portable HTML file using the Python standard library."""
from base64 import b64encode
from pathlib import Path

root = Path(__file__).resolve().parents[1]
page = (root / 'index.html').read_text(encoding='utf-8')
css = (root / 'style.css').read_text(encoding='utf-8')
page = page.replace('<link rel="stylesheet" href="style.css">', f'<style>\n{css}\n</style>')
script = (root / 'script.js').read_text(encoding='utf-8')
page = page.replace('<script src="script.js" defer></script>', '')
page = page.replace('</body>', f'<script>\n{script}\n</script>\n</body>')
for name in ('mark.svg', 'staircase.svg'):
    encoded = b64encode((root / 'assets' / name).read_bytes()).decode('ascii')
    page = page.replace(f'assets/{name}', f'data:image/svg+xml;base64,{encoded}')
(root / 'site.html').write_text(page, encoding='utf-8')
print('site.html')
