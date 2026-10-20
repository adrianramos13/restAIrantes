// Diario / Eatlist del Perfil: grupos (p. ej. por mes) de filas con un recuadro (día o puesto), la foto, el
// nombre y, si hay, la nota en estrellas y un icono si tiene comentario. Al tocar una fila se avisa a Python
// ("abrir", con el id del restaurante) para abrir su ficha.
const ICONO_COMENTARIO = '<svg class="icono" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16v2H4zm0 5h16v2H4zm0 5h10v2H4z"/></svg>';

export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const raiz = parentElement.querySelector('.diario');
  raiz.textContent = '';
  (data.grupos || []).forEach((grupo) => {
    if (grupo.titulo) {
      const mes = document.createElement('div'); mes.className = 'mes'; mes.textContent = grupo.titulo;
      raiz.appendChild(mes);
    }
    const filas = document.createElement('ul'); filas.className = 'filas'; filas.setAttribute('role', 'list');
    grupo.items.forEach((r) => {
      const li = document.createElement('li');
      const fila = document.createElement('button'); fila.type = 'button'; fila.className = 'fila';
      const partes = [data.puestos ? `Puesto ${r.caja}` : `Día ${r.caja}`, r.nombre, r.detalle,
        r.nota != null && `${String(r.nota).replace('.', ',')} de 5 estrellas`, r.comentario && 'con comentario', 'Ver ficha'];
      fila.setAttribute('aria-label', partes.filter(Boolean).join('. '));

      const caja = document.createElement('span'); caja.className = 'caja' + (data.puestos ? ' puesto' : '');
      caja.textContent = r.caja; caja.setAttribute('aria-hidden', 'true');
      const foto = document.createElement('span'); foto.className = 'foto'; foto.setAttribute('aria-hidden', 'true');
      foto.textContent = (r.nombre.trim()[0] || '?').toUpperCase();
      if (r.foto) {
        const img = document.createElement('img'); img.alt = ''; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer';
        img.src = r.foto; img.onload = () => { foto.textContent = ''; foto.appendChild(img); };
      }
      const info = document.createElement('span'); info.className = 'info';
      const nombre = document.createElement('span'); nombre.className = 'nombre'; nombre.textContent = r.nombre + ' ';
      if (r.detalle) {
        const detalle = document.createElement('span'); detalle.className = 'detalle'; detalle.textContent = r.detalle;
        nombre.appendChild(detalle);
      }
      info.appendChild(nombre);
      if (r.nota != null || r.comentario) {
        const linea = document.createElement('span'); linea.className = 'linea';
        if (r.nota != null) {
          const estrellas = document.createElement('span'); estrellas.className = 'estrellas'; estrellas.setAttribute('aria-hidden', 'true');
          const fondo = document.createElement('span'); fondo.className = 'fondo'; fondo.textContent = '★★★★★';
          const relleno = document.createElement('span'); relleno.className = 'relleno'; relleno.textContent = '★★★★★';
          relleno.style.width = `${(r.nota / 5) * 100}%`;
          estrellas.append(fondo, relleno);
          linea.appendChild(estrellas);
        }
        if (r.comentario) linea.insertAdjacentHTML('beforeend', ICONO_COMENTARIO);
        info.appendChild(linea);
      }
      fila.append(caja, foto, info);
      fila.onclick = () => setTriggerValue('abrir', r.id);
      li.appendChild(fila);
      filas.appendChild(li);
    });
    raiz.appendChild(filas);
  });
}
