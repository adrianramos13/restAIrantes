export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const avatar = parentElement.querySelector('.avatar');
  const menu = parentElement.querySelector('.menu');
  const img = avatar.querySelector('img');
  const inicial = avatar.querySelector('.inicial');

  avatar.setAttribute('aria-label', `Menú de usuario de ${data.nombre || 'tu cuenta'}`);
  inicial.textContent = data.inicial || '?';
  if (data.foto) {
    img.onerror = () => { img.hidden = true; inicial.hidden = false; };   // la foto de Google puede fallar
    img.src = data.foto;
    img.hidden = false;
    inicial.hidden = true;
  }

  const abrir = (si) => {
    menu.hidden = !si;
    avatar.setAttribute('aria-expanded', String(si));
    if (si) menu.querySelector('[role="menuitem"]').focus();
  };
  avatar.onclick = () => abrir(menu.hidden);
  menu.querySelectorAll('[role="menuitem"]').forEach((opcion) => {
    opcion.onclick = () => { abrir(false); setTriggerValue('opcion', opcion.dataset.opcion); };
  });
  parentElement.onkeydown = (e) => { if (e.key === 'Escape' && !menu.hidden) { abrir(false); avatar.focus(); } };

  // Cerrar al pulsar fuera (el listener se registra una vez por componente montado).
  if (!parentElement.__cerrarFuera) {
    parentElement.__cerrarFuera = (e) => { if (!e.composedPath().includes(parentElement)) abrir(false); };
    document.addEventListener('click', parentElement.__cerrarFuera);
  }
  return () => {
    document.removeEventListener('click', parentElement.__cerrarFuera);
    parentElement.__cerrarFuera = null;
  };
}
