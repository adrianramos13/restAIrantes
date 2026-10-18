// Buscar amigos: según se escribe, se enseñan las personas cuyo nombre o @usuario contiene el texto (sin
// tildes ni mayúsculas). Solo llegan aquí nombre y @usuario, nunca correos. "Añadir" avisa a Python con el
// @usuario y Python envía la solicitud.
const MAX_RESULTADOS = 8;
const normalizar = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const input = parentElement.querySelector('input');
  const lista = parentElement.querySelector('.resultados');
  const vacio = parentElement.querySelector('.vacio');
  const personas = data.personas || [];

  const pintar = () => {
    const texto = normalizar(input.value.trim().replace(/^@/, ''));
    lista.textContent = '';
    if (!texto) { vacio.hidden = true; return; }
    const encontradas = personas
      .filter((p) => normalizar(p.nombre).includes(texto) || normalizar(p.alias).includes(texto))
      .slice(0, MAX_RESULTADOS);
    vacio.hidden = encontradas.length > 0;
    encontradas.forEach((p) => {
      const li = document.createElement('li'); li.className = 'resultado';
      const avatar = document.createElement('span'); avatar.className = 'avatar';
      avatar.style.background = p.color; avatar.textContent = p.inicial; avatar.setAttribute('aria-hidden', 'true');
      const quien = document.createElement('span'); quien.className = 'quien';
      const nombre = document.createElement('span'); nombre.className = 'nombre'; nombre.textContent = p.nombre;
      const alias = document.createElement('span'); alias.className = 'alias'; alias.textContent = `@${p.alias}`;
      quien.append(nombre, alias);
      li.append(avatar, quien);
      if (p.estado === 'nuevo') {
        const boton = document.createElement('button'); boton.type = 'button'; boton.className = 'anadir';
        boton.textContent = 'Añadir'; boton.setAttribute('aria-label', `Añadir a ${p.nombre} como amigo`);
        boton.onclick = () => { boton.disabled = true; boton.textContent = 'Enviando…'; setTriggerValue('anadir', p.alias); };
        li.appendChild(boton);
      } else {
        const estado = document.createElement('span'); estado.className = 'estado';
        estado.textContent = p.estado === 'amigo' ? 'Amigos ✓' : 'Pendiente';
        li.appendChild(estado);
      }
      lista.appendChild(li);
    });
  };
  input.oninput = pintar;
  pintar();   // al volver a dibujarse (p. ej. tras "Añadir"), sigue lo que habías escrito
}
