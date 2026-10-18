export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const botones = parentElement.querySelectorAll('[data-seccion]');
  botones.forEach((boton) => {
    const activa = boton.dataset.seccion === data.activa;
    if (activa) boton.setAttribute('aria-current', 'page'); else boton.removeAttribute('aria-current');
    boton.onclick = () => { if (!activa) setTriggerValue('seccion', boton.dataset.seccion); };
  });

  // Perfil: la foto de Google del usuario; si no hay (modo local) o falla, el icono de persona.
  const img = parentElement.querySelector('.avatar img');
  const persona = parentElement.querySelector('.avatar .persona');
  const sinFoto = () => { img.hidden = true; persona.hidden = false; };
  if (data.foto) {
    img.onerror = sinFoto;
    img.src = data.foto;
    img.hidden = false;
    persona.hidden = true;
  } else {
    sinFoto();
  }

  // Globito con las solicitudes de amistad pendientes, sobre el icono de Perfil.
  const perfil = parentElement.querySelector('[data-seccion="perfil"]');
  const avatar = perfil.querySelector('.avatar');
  let globo = perfil.querySelector('.aviso');
  if (data.avisos > 0) {
    if (!globo) { globo = document.createElement('span'); globo.className = 'aviso'; avatar.after(globo); }
    globo.textContent = data.avisos > 9 ? '9+' : String(data.avisos);
    perfil.setAttribute('aria-label', `Perfil, ${data.avisos} ${data.avisos === 1 ? 'solicitud' : 'solicitudes'} de amistad`);
  } else {
    if (globo) globo.remove();
    perfil.removeAttribute('aria-label');
  }
}
