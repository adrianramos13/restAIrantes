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
}
