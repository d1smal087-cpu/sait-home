const themeColors = { warm: '#eee9df', dark: '#191c1e', light: '#ffffff' };
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]').content = themeColors[theme];
  document.querySelectorAll('[data-theme-choice]').forEach((button) => {
    button.setAttribute('aria-pressed', String(button.dataset.themeChoice === theme));
  });
}
const requestedTheme = new URLSearchParams(location.search).get('theme');
applyTheme(Object.hasOwn(themeColors, requestedTheme) ? requestedTheme : document.documentElement.dataset.theme);
document.querySelectorAll('[data-theme-choice]').forEach((button) => {
  button.addEventListener('click', () => {
    applyTheme(button.dataset.themeChoice);
    // Some browsers restrict history updates when opening local files.
    try {
      const url = new URL(location.href);
      url.searchParams.set('theme', button.dataset.themeChoice);
      history.replaceState(null, '', url);
    } catch { /* Switching still works without updating the address. */ }
  });
});

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
document.querySelector('#brief-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const place = document.querySelector('#place').value;
  const wish = document.querySelector('#wish').value.trim();
  document.querySelector('#brief-text').value = `Здравствуйте! Хочу обсудить изготовление лестницы в «Мире ступеней».\nГород: Кемерово.\nРасположение: ${place.toLowerCase()}.\n${wish ? `Пожелания: ${wish}` : 'Хочу обсудить варианты конструкции и материалов.'}`;
  document.querySelector('#brief-result').hidden = false;
  document.querySelector('#copy-status').textContent = '';
  document.querySelector('#brief-text').focus();
});
document.querySelector('#copy-brief').addEventListener('click', async () => {
  const field = document.querySelector('#brief-text');
  const status = document.querySelector('#copy-status');
  try {
    await navigator.clipboard.writeText(field.value);
    status.textContent = 'Описание скопировано.';
  } catch {
    field.focus();
    field.select();
    status.textContent = 'Текст выделен. Скопируйте его через меню устройства или Ctrl+C.';
  }
});
