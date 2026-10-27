const menu = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#navigation');
function closeMenu() {
  navigation.classList.remove('open');
  menu.setAttribute('aria-expanded', 'false');
}
menu.addEventListener('click', () => {
  const open = menu.getAttribute('aria-expanded') !== 'true';
  navigation.classList.toggle('open', open);
  menu.setAttribute('aria-expanded', String(open));
});
navigation.addEventListener('click', (event) => {
  if (event.target.closest('a')) closeMenu();
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && menu.getAttribute('aria-expanded') === 'true') {
    closeMenu();
    menu.focus();
  }
});
const workLinks = [...document.querySelectorAll('[data-gallery]')];
const viewer = document.querySelector('#work-viewer');
if (viewer && typeof viewer.showModal === 'function') {
  const photos = workLinks.flatMap((link) => [
    { src: link.href, alt: link.querySelector('img').alt, title: link.dataset.title, label: 'Общий вид' },
    { src: link.dataset.detail, alt: link.dataset.detailAlt, title: link.dataset.title, label: 'Деталь проекта' },
  ]);
  let currentPhoto = 0;
  let lastTrigger;
  function showPhoto(index) {
    currentPhoto = (index + photos.length) % photos.length;
    const photo = photos[currentPhoto];
    const image = document.querySelector('#work-image');
    image.src = photo.src;
    image.alt = photo.alt;
    document.querySelector('#work-title').textContent = photo.title;
    document.querySelector('#work-counter').textContent = `${currentPhoto + 1} / ${photos.length} · ${photo.label}`;
  }
  workLinks.forEach((link, index) => {
    link.addEventListener('click', (event) => {
      if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      lastTrigger = link;
      showPhoto(index * 2);
      viewer.showModal();
      document.body.classList.add('viewer-open');
    });
  });
  document.querySelector('#work-prev').addEventListener('click', () => showPhoto(currentPhoto - 1));
  document.querySelector('#work-next').addEventListener('click', () => showPhoto(currentPhoto + 1));
  viewer.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      showPhoto(currentPhoto + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
  viewer.addEventListener('click', (event) => {
    if (event.target !== viewer) return;
    const rect = viewer.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) viewer.close();
  });
  viewer.addEventListener('close', () => {
    document.body.classList.remove('viewer-open');
    lastTrigger?.focus({ preventScroll: true });
  });
}
