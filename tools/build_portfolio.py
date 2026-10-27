"""Generate a static catalog and a shareable page for each object."""
from html import escape
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def plural(n, forms):
    return forms[2] if 11 <= n % 100 <= 14 else forms[0] if n % 10 == 1 else forms[1] if 2 <= n % 10 <= 4 else forms[2]


def main():
    data = json.loads((ROOT / 'portfolio.json').read_text())
    albums = data['albums']
    source = (ROOT / 'index.html').read_text()
    header = re.search(r'  <header[\s\S]*?</header>', source)[0]
    footer = re.search(r'  <footer[\s\S]*?</footer>', source)[0]
    viewer = re.search(r'  <dialog[\s\S]*?</dialog>', source)[0]
    (ROOT / 'works').mkdir(exist_ok=True)

    def page(title, description, content, nested=False, gallery=False):
        prefix = '../' if nested else ''
        nav = header.replace('href="#', f'href="{prefix}index.html#')
        nav = nav.replace('href="works.html"', f'href="{prefix}works.html" aria-current="page"')
        nav = nav.replace('src="assets/', f'src="{prefix}assets/')
        foot = footer.replace('href="#"', f'href="{prefix}index.html"', 1)
        foot = foot.replace('src="assets/', f'src="{prefix}assets/')
        return f'''<!doctype html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#6e6f5d">
  <meta name="description" content="{escape(description, quote=True)}">
  <title>{escape(title)} — Мир ступеней, Кемерово</title>
  <link rel="icon" href="{prefix}assets/mark.svg" type="image/svg+xml">
  <link rel="stylesheet" href="{prefix}style.css">
  <script src="{prefix}script.js" defer></script>
</head>
<body id="top">
{nav}
  <main class="wrap portfolio-page">
{content}
  </main>
{foot}
{viewer if gallery else ''}
</body>
</html>
'''

    cards = []
    total = sum(len(a['photos']) for a in albums)
    ready = sum(bool(a['photos']) for a in albums)
    for album in sorted(albums, key=lambda album: not album['photos']):
        count = len(album['photos'])
        href = f'works/{album["id"]}.html'
        status = f'{count} {plural(count, ("фотография", "фотографии", "фотографий"))}' if count else 'Фотографии скоро'
        if count:
            # Stable editorial covers for the previously selected objects.
            cover_indices = {'Виталий Жур Гор': 9, 'Павел СНТ Метал': 2, 'Денис Бульвар': 35,
                             'Юрий МП': 40, 'Никита ЛП': 25, 'Яшкино': 0}
            cover = album['photos'][min(cover_indices.get(album['title'], 0), count - 1)]
            art = f'<img src="{cover["thumb"]}" alt="Один из наших проектов лестницы" loading="lazy" decoding="async" width="{cover["width"]}" height="{cover["height"]}">'
        else:
            art = '<span class="album-placeholder"><img src="assets/mark.svg" width="64" height="64" alt=""><span>Фотографии скоро</span></span>'
        cards.append(f'''      <article class="card album-card" data-album-status="{'photos' if count else 'pending'}">
        <a class="album-link" href="{href}" aria-label="Открыть альбом: {status}">
          <div class="album-cover">{art}<span class="photo-hint">{'Смотреть объект' if count else 'Об объекте'}</span></div>
          <p class="album-count">{status}</p>
        </a>
      </article>''')
        photos_html = []
        for index, photo in enumerate(album['photos'], 1):
            alt = f'Лестница — фотография {index}'
            photos_html.append(f'''      <a class="album-photo" href="../{photo['src']}" data-gallery data-single data-title="Фотографии объекта" aria-label="Открыть фотографию {index}">
        <img src="../{photo['thumb']}" alt="{alt}" loading="lazy" decoding="async" width="{photo['width']}" height="{photo['height']}">
        <span class="photo-hint">{index} / {count}</span>
      </a>''')
        gallery = '<div class="album-photos">\n' + '\n'.join(photos_html) + '\n    </div>' if count else '''<div class="empty-album"><img src="../assets/mark.svg" width="72" height="72" alt=""><h2>Фотографии скоро</h2><p>Объект уже в каталоге. Фотографии добавим, когда они появятся.</p><a class="button" href="../works.html">Посмотреть другие объекты <span>↗</span></a></div>'''
        video_note = f'<p class="album-video-note">На Яндекс Диске также доступны видео наших работ.</p>' if album['videos'] else ''
        content = f'''    <nav class="breadcrumbs" aria-label="Хлебные крошки"><a href="../index.html">Главная</a><span aria-hidden="true">/</span><a href="../works.html">Все работы</a></nav>
    <div class="portfolio-heading"><p class="eyebrow">Наши работы</p><h1>Фотографии объекта</h1><p>{status}{' · Нажмите на снимок, чтобы рассмотреть детали.' if count else ''}</p></div>
    {gallery}
    <div class="album-bottom"><a class="button" href="../works.html">Все объекты <span>↗</span></a><a class="text-link" href="tel:+79960402972">Обсудить похожую лестницу: +7 996 040-29-72</a></div>
    {video_note}
    {f'<a class="text-link" href="{escape(data["source"])}" target="_blank" rel="noopener noreferrer">Открыть материалы на Яндекс Диске</a>' if album['videos'] else ''}'''
        (ROOT / 'works' / f'{album["id"]}.html').write_text(page('Фотографии объекта', f'{status}. Изготовление лестниц в Кемерово — Мир ступеней.', content, nested=True, gallery=bool(count)))
    content = f'''    <div class="breadcrumbs"><a href="index.html">← На главную</a></div>
    <div class="portfolio-heading"><p class="eyebrow">Мир ступеней · портфолио</p><h1>Все наши <em>работы.</em></h1><p>{len(albums)} объектов · {total} фотографий. У каждого объекта — свой альбом.</p></div>
    <div class="album-filters" role="group" aria-label="Показать объекты" hidden>
      <button type="button" data-album-filter="all" aria-pressed="true">Все объекты · {len(albums)}</button>
      <button type="button" data-album-filter="photos" aria-pressed="false">С фотографиями · {ready}</button>
      <button type="button" data-album-filter="pending" aria-pressed="false">Ожидают фото · {len(albums) - ready}</button>
    </div>
    <p id="album-filter-status" class="sr-only" role="status"></p>
    <div class="cards album-cards">
{chr(10).join(cards)}
    </div>
    <div class="portfolio-social"><div><h3>Обсудим вашу лестницу?</h3><p>Позвоните нам или посмотрите подробности работ в нашем сообществе.</p></div><a class="button" href="https://vk.ru/mirstupeney" target="_blank" rel="noopener noreferrer">Смотреть ВКонтакте <span>↗</span></a></div>'''
    (ROOT / 'works.html').write_text(page('Все работы', f'{len(albums)} объектов и {total} фотографий лестниц. Портфолио мастерской Мир ступеней в Кемерово.', content))
    print(f'Built works.html and {len(albums)} object pages')


if __name__ == '__main__':
    main()
