// Ставит сохранённую тему до отрисовки, чтобы не было вспышки тёмного/светлого.
try { if (localStorage.getItem('rz.theme') === 'light') document.documentElement.dataset.theme = 'light' } catch (e) {}
