"""Import public Yandex Disk photographs. Requires Pillow; no credentials needed.

Usage: python3 tools/import_portfolio.py
Only photographs and public folder names are published; source documents stay on Disk.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import hashlib
import json
import time

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SHARE = 'https://disk.yandex.ru/d/mNWcqCfuPH3YpA'
ASSETS = ROOT / 'assets' / 'projects'
ASSETS.mkdir(exist_ok=True)


def read_url(url):
    for attempt in range(4):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'MirStupeneyPortfolio/1.0'}), timeout=60) as response:
                return response.read()
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


def listing(path):
    items = []
    while True:
        query = urlencode(dict(public_key=SHARE, path=path, limit=200, offset=len(items),
                               preview_size='1600x1600', preview_crop='false'))
        data = json.loads(read_url('https://cloud-api.yandex.net/v1/disk/public/resources?' + query))
        embedded = data.get('_embedded', {})
        items.extend(embedded.get('items', []))
        if len(items) >= embedded.get('total', 0):
            return items


def image_key(item):
    return hashlib.sha256((item['path'] + item.get('md5', '')).encode()).hexdigest()[:16]


def download(item):
    key = image_key(item)
    target = ASSETS / (key + '.webp')
    thumb = ASSETS / (key + '-thumb.webp')
    if not target.exists() or not thumb.exists():
        raw = read_url(item['preview'])
        with Image.open(BytesIO(raw)) as source:
            photo = ImageOps.exif_transpose(source).convert('RGB')
            photo.thumbnail((1600, 1600))
            photo.save(target, 'WEBP', quality=82, method=4)
            photo.thumbnail((560, 560))
            photo.save(thumb, 'WEBP', quality=78, method=4)
    with Image.open(target) as photo:
        width, height = photo.size
    return dict(src=f'assets/projects/{target.name}', thumb=f'assets/projects/{thumb.name}',
                width=width, height=height)


def main():
    folders = sorted((f for f in listing('/') if f['type'] == 'dir'), key=lambda f: f['name'].casefold())
    albums = []
    jobs = []
    for number, folder in enumerate(folders, 1):
        queue = [folder['path']]
        files = []
        while queue:
            items = listing(queue.pop(0))
            files.extend(f for f in items if f['type'] == 'file')
            queue.extend(f['path'] for f in items if f['type'] == 'dir')
        photos = sorted((f for f in files if f.get('mime_type', '').startswith('image/') and f.get('preview')),
                        key=lambda f: f['path'])
        album = dict(id=f'object-{number:02}', title=folder['name'], photos=[None] * len(photos),
                     videos=sum(f.get('mime_type', '').startswith('video/') for f in files))
        albums.append(album)
        jobs.extend((album, index, photo) for index, photo in enumerate(photos))
        print(f'Folder {number}/{len(folders)}: {len(photos)} photos', flush=True)
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(download, photo): (album, index) for album, index, photo in jobs}
        for count, future in enumerate(as_completed(futures), 1):
            album, index = futures[future]
            album['photos'][index] = future.result()
            if count % 25 == 0 or count == len(jobs):
                print(f'Prepared {count}/{len(jobs)} photographs', flush=True)
    # Publish only after every import succeeds: no half-written manifest.
    manifest = dict(source=SHARE, albums=albums)
    (ROOT / 'portfolio.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(f'Done: {len(albums)} objects, {len(jobs)} photographs', flush=True)


if __name__ == '__main__':
    main()
