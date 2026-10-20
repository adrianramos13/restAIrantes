// Tus amigos como la lista de seguidores de Instagram: buscador (filtra aquí, sin tildes ni mayúsculas) y una
// fila por amigo; al tocarla se avisa a Python ("abrir", con su @usuario) para abrir su mini perfil.
const normalizar = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const input = parentElement.querySelector('input');
  const filas = parentElement.querySelector('.filas');
  const vacio = parentElement.querySelector('.vacio');
  const personas = data.personas || [];

  const pintar = () => {
    const texto = normalizar(input.value.trim().replace(/^@/, ''));
    filas.textContent = '';
    const vistas = personas.filter((p) => !texto || normalizar(p.nombre).includes(texto) || normalizar(p.alias).includes(texto));
    vacio.hidden = vistas.length > 0;
    vistas.forEach((p) => {
      const li = document.createElement('li');
      const fila = document.createElement('button'); fila.type = 'button'; fila.className = 'fila';
      fila.setAttribute('aria-label', `${p.alias ? '@' + p.alias + ', ' : ''}${p.nombre}. Ver su perfil`);
      const avatar = document.createElement('span'); avatar.className = 'avatar'; avatar.setAttribute('aria-hidden', 'true');
      avatar.style.background = p.color; avatar.textContent = p.inicial;
      if (p.foto) {
        const img = document.createElement('img'); img.alt = ''; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer';
        img.src = p.foto; img.onerror = () => img.remove();
        avatar.appendChild(img);
      }
      const quien = document.createElement('span'); quien.className = 'quien';
      const alias = document.createElement('span'); alias.className = 'alias'; alias.textContent = p.alias || p.nombre;
      quien.appendChild(alias);
      if (p.alias) {
        const nombre = document.createElement('span'); nombre.className = 'nombre'; nombre.textContent = p.nombre;
        quien.appendChild(nombre);
      }
      fila.append(avatar, quien);
      fila.onclick = () => setTriggerValue('abrir', p.clave);
      li.appendChild(fila);
      filas.appendChild(li);
    });
  };
  input.oninput = pintar;
  pintar();
}
