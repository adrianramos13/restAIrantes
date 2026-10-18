// Fila de amigos: círculo (foto de Google o inicial sobre su color) y nombre debajo. Al tocar uno se avisa a
// Python ("abrir", con su @usuario) para abrir su mini perfil.
export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const fila = parentElement.querySelector('.fila');
  fila.textContent = '';
  (data.personas || []).forEach((p) => {
    const li = document.createElement('li');
    const boton = document.createElement('button');
    boton.type = 'button'; boton.className = 'persona';
    boton.setAttribute('aria-label',
      `${p.nombre}${p.alias ? ', @' + p.alias : ''}${p.detalle ? '. ' + p.detalle : ''}. Ver su perfil`);

    const avatar = document.createElement('span'); avatar.className = 'avatar'; avatar.style.background = p.color;
    const inicial = document.createElement('span'); inicial.className = 'inicial'; inicial.textContent = p.inicial;
    avatar.appendChild(inicial);
    if (p.foto) {
      const img = document.createElement('img');
      img.alt = ''; img.referrerPolicy = 'no-referrer'; img.loading = 'lazy'; img.src = p.foto;
      img.onerror = () => img.remove();   // si la foto falla, queda la inicial
      avatar.appendChild(img);
    }
    const nombre = document.createElement('span'); nombre.className = 'nombre'; nombre.textContent = p.nombre;
    boton.append(avatar, nombre);
    if (p.alias) {
      const alias = document.createElement('span'); alias.className = 'alias'; alias.textContent = `@${p.alias}`;
      boton.appendChild(alias);
    }
    if (p.detalle) {
      const detalle = document.createElement('span'); detalle.className = 'detalle'; detalle.textContent = p.detalle;
      boton.appendChild(detalle);
    }
    boton.onclick = () => setTriggerValue('abrir', p.clave);
    li.appendChild(boton);
    fila.appendChild(li);
  });
}
