
const PHOTON = 'https://photon.komoot.io/api/';
const CAJA_MADRID = '-4.58,39.88,-3.05,41.17';   // lon/lat mín,máx: Comunidad de Madrid

function etiquetas(p) {
  const calle = [p.street, p.housenumber].filter(Boolean).join(' ');
  const principal = p.name || calle || p.district || p.city || '';
  const detalle = [p.name ? calle : null, p.district, p.city].filter((x) => x && x !== principal);
  return { principal, detalle: [...new Set(detalle)].join(', ') };
}

export default function (component) {
  const { parentElement, data, setStateValue } = component;
  const input = parentElement.querySelector('#dir');
  const lista = parentElement.querySelector('#sugerencias');
  let opciones = [], activa = -1, temporizador = null, peticion = 0;

  input.disabled = !!data.disabled;
  input.placeholder = data.placeholder || '';
  if (!input.value && data.texto) input.value = data.texto;   // si la caja se ha vuelto a montar vacía

  const cerrar = () => { lista.hidden = true; input.setAttribute('aria-expanded', 'false'); activa = -1; };
  const enviarTexto = () => { if (input.value !== (data.texto || '')) setStateValue('texto', input.value); };

  const elegir = (i) => {
    const o = opciones[i];
    input.value = o.texto;
    cerrar();
    setStateValue('seleccion', { lat: o.lat, lon: o.lon, texto: o.texto });
    setStateValue('texto', o.texto);
  };

  const pintar = () => {
    lista.innerHTML = '';
    opciones.forEach((o, i) => {
      const li = document.createElement('li');
      li.setAttribute('role', 'option');
      li.setAttribute('aria-selected', String(i === activa));
      const a = document.createElement('span'); a.className = 'principal'; a.textContent = o.principal;
      const b = document.createElement('span'); b.className = 'detalle'; b.textContent = o.detalle;
      li.append(a, b);
      li.onmousedown = (e) => { e.preventDefault(); elegir(i); };   // mousedown: antes del blur
      lista.appendChild(li);
    });
    lista.hidden = opciones.length === 0;
    input.setAttribute('aria-expanded', String(!lista.hidden));
  };

  input.oninput = () => {
    clearTimeout(temporizador);
    const q = input.value.trim();
    if (q.length < 3) { opciones = []; cerrar(); return; }
    temporizador = setTimeout(async () => {
      const id = ++peticion;
      try {
        const url = `${PHOTON}?q=${encodeURIComponent(q)}&limit=6&lat=40.4168&lon=-3.7038&bbox=${CAJA_MADRID}`;
        const res = await (await fetch(url)).json();
        if (id !== peticion) return;   // ya hay una petición más reciente
        const vistos = new Set();
        opciones = res.features.map((f) => {
          const { principal, detalle } = etiquetas(f.properties);
          const [lon, lat] = f.geometry.coordinates;
          return { principal, detalle, lat, lon, texto: [principal, detalle].filter(Boolean).join(', ') };
        }).filter((o) => o.principal && !vistos.has(o.texto) && vistos.add(o.texto));
        activa = -1;
        pintar();
      } catch (e) { opciones = []; cerrar(); }   // sin sugerencias: se puede seguir escribiendo a mano
    }, 300);
  };

  input.onkeydown = (e) => {
    if (e.key === 'ArrowDown' && opciones.length) { activa = (activa + 1) % opciones.length; pintar(); e.preventDefault(); }
    else if (e.key === 'ArrowUp' && opciones.length) { activa = (activa - 1 + opciones.length) % opciones.length; pintar(); e.preventDefault(); }
    else if (e.key === 'Enter') { if (activa >= 0 && !lista.hidden) elegir(activa); else { cerrar(); enviarTexto(); } }
    else if (e.key === 'Escape') cerrar();
  };
  input.onblur = () => { cerrar(); enviarTexto(); };
}
