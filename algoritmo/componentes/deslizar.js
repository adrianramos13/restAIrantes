// «Food match»: pila de tarjetas. Arrastrar a la derecha (o ♥) = me gusta; a la izquierda (o ✕) = no.
// Python manda las tarjetas pendientes (data.tarjetas, la primera es la de arriba) y recibe cada decisión por el
// trigger «decision» = {id, gusta}. La pila vive aquí: las tarjetas nuevas se meten por debajo sin redibujar las
// que ya están, así que no hay parpadeos mientras Python guarda y manda la siguiente tanda.
const UMBRAL_PX = 100;   // lo que hay que arrastrar para que cuente
const ZOOM_MAPA = 16;
const ZOOM_PREVIA = 14;
const AMPLIAR_MS = 260;   // lo que dura la animación de .dz-mapa en deslizar.css
const LEAFLET_CSS = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css';
const LEAFLET_JS = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js';

// Leaflet solo se pide al abrir el primer mapa (misma promesa que mapa.js, por si ya está cargado)
function cargarLeaflet() {
  if (window.L && window.L.map) return Promise.resolve(window.L);
  if (!window.__fmLeaflet) {
    const cargar = (el) => new Promise((ok, fallo) => { el.onload = ok; el.onerror = fallo; document.head.appendChild(el); });
    const css = Object.assign(document.createElement('link'), { rel: 'stylesheet', href: LEAFLET_CSS });
    const js = Object.assign(document.createElement('script'), { src: LEAFLET_JS });
    window.__fmLeaflet = Promise.all([cargar(css), cargar(js)]).then(() => window.L)
      .catch((e) => { window.__fmLeaflet = null; throw e; });
  }
  return window.__fmLeaflet;
}

// Un solo mapa por tarjeta: pequeño en la esquina (vista previa, quieto) y, al tocarlo, a toda la tarjeta con
// zoom (+/− o pellizcando). Solo se crea para las tarjetas que se ven (la de arriba y la de debajo).
const MANEJADORES = ['dragging', 'touchZoom', 'scrollWheelZoom', 'doubleClickZoom', 'keyboard'];

async function prepararMapa(t) {
  if (!t || !t.__r || t.__mapa || t.__cargando) return;
  t.__cargando = true;
  const { __r: r, __base: base } = t;
  const div = t.querySelector('.dz-mapa');
  try {
    const L = await cargarLeaflet();
    if (!t.isConnected) return;
    const mapa = L.map(div, { zoomControl: false, dragging: false, touchZoom: false, scrollWheelZoom: false,
      doubleClickZoom: false, boxZoom: false, keyboard: false }).setView([r.lat, r.lon], ZOOM_PREVIA);
    mapa.attributionControl.setPrefix(false);
    L.tileLayer(base.url, { maxZoom: base.maxZoom || 19, attribution: base.atribucion || '' }).addTo(mapa);
    L.circleMarker([r.lat, r.lon], { radius: 8, color: '#FFFFFF', weight: 3, fillColor: '#DC2626', fillOpacity: 1 })
      .addTo(mapa);
    t.__mapa = mapa;
    t.__zoom = L.control.zoom();
  } catch (e) {
    div.remove();   // sin internet para el mapa: la tarjeta se queda sin vista previa
  } finally {
    t.__cargando = false;
  }
}

function ampliarMapa(t, abrir) {
  const mapa = t.__mapa;
  if (!mapa || t.classList.contains('dz-con-mapa') === abrir) return;
  t.classList.toggle('dz-con-mapa', abrir);
  for (const m of MANEJADORES) mapa[m][abrir ? 'enable' : 'disable']();
  if (abrir) t.__zoom.addTo(mapa); else t.__zoom.remove();
  const centrar = () => { mapa.invalidateSize(); mapa.setView([t.__r.lat, t.__r.lon], abrir ? ZOOM_MAPA : ZOOM_PREVIA); };
  centrar();
  setTimeout(centrar, AMPLIAR_MS);   // otra vez al acabar la animación de tamaño
}

function texto(etiqueta, clase, contenido) {
  const e = document.createElement(etiqueta); e.className = clase; e.textContent = contenido;
  return e;
}

function inicial(nombre) {
  return texto('div', 'dz-sin-foto', (nombre || '?').trim().charAt(0).toUpperCase());
}

function tarjeta(r, base) {
  const t = document.createElement('div');
  t.className = 'dz-tarjeta';
  t.dataset.id = String(r.id);
  t.setAttribute('role', 'group');
  t.setAttribute('aria-label', r.nombre);
  if (r.foto) {
    const img = document.createElement('img');
    img.className = 'dz-foto'; img.alt = ''; img.draggable = false; img.src = r.foto;   // se descargan ya: precarga
    img.onerror = () => img.replaceWith(inicial(r.nombre));
    t.append(img);
  } else {
    t.append(inicial(r.nombre));
  }
  if (r.lat != null && r.lon != null) {
    t.__r = r; t.__base = base;
    const previa = texto('div', 'dz-mapa', '');
    previa.setAttribute('role', 'button'); previa.tabIndex = 0;
    previa.setAttribute('aria-label', 'Ver el mapa en grande');
    previa.addEventListener('click', () => ampliarMapa(t, true));
    previa.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') ampliarMapa(t, true); });
    const cerrar = texto('button', 'dz-cerrar-mapa', '✕');
    cerrar.type = 'button';
    cerrar.setAttribute('aria-label', 'Cerrar el mapa');
    cerrar.onclick = () => ampliarMapa(t, false);
    t.append(previa, cerrar);
  }
  const info = document.createElement('div'); info.className = 'dz-info';
  info.append(texto('div', 'dz-nombre', r.nombre));
  if (r.localidad) info.append(texto('div', 'dz-localidad', `📍 ${r.localidad}`));
  if (r.meta) info.append(texto('div', 'dz-meta', r.meta));
  if (r.motivo) info.append(texto('div', 'dz-motivo', r.motivo));
  t.append(info, texto('div', 'dz-sello dz-sello-si', 'ME GUSTA'), texto('div', 'dz-sello dz-sello-no', 'PASO'));
  return t;
}

export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const mazo = parentElement.querySelector('.dz-mazo');
  const estado = parentElement.__dz || (parentElement.__dz = { decididos: new Set() });
  const [botonNo, botonSi] = parentElement.querySelectorAll('.dz-boton');
  // la de arriba: la última que no se esté yendo ya
  const arriba = () => [...mazo.children].reverse().find((t) => !estado.decididos.has(t.dataset.id));
  const botones = () => {
    botonNo.disabled = botonSi.disabled = !arriba();
    [...mazo.children].filter((t) => !estado.decididos.has(t.dataset.id)).slice(-2).forEach(prepararMapa);
  };

  function decidir(t, gusta) {
    if (!t || estado.decididos.has(t.dataset.id)) return;
    estado.decididos.add(t.dataset.id);
    t.style.transform = `translateX(${gusta ? 150 : -150}%) rotate(${gusta ? 25 : -25}deg)`;
    t.style.opacity = '0';
    setTimeout(() => { if (t.__mapa) t.__mapa.remove(); t.remove(); }, 260);
    botones();
    setTriggerValue('decision', { id: Number(t.dataset.id), gusta });
  }

  function arrastrable(t) {
    let x0 = null, dx = 0;
    const si = t.querySelector('.dz-sello-si'), no = t.querySelector('.dz-sello-no');
    t.addEventListener('pointerdown', (e) => {
      if (t !== arriba() || e.target.closest('.dz-mapa, .dz-cerrar-mapa')) return;   // en el mapa se arrastra el mapa
      x0 = e.clientX; dx = 0;
      t.classList.add('dz-arrastrando');
      t.setPointerCapture(e.pointerId);
    });
    t.addEventListener('pointermove', (e) => {
      if (x0 === null) return;
      dx = e.clientX - x0;
      t.style.transform = `translateX(${dx}px) rotate(${dx / 18}deg)`;
      si.style.opacity = String(Math.max(0, Math.min(1, dx / UMBRAL_PX)));
      no.style.opacity = String(Math.max(0, Math.min(1, -dx / UMBRAL_PX)));
    });
    const soltar = () => {
      if (x0 === null) return;
      x0 = null;
      t.classList.remove('dz-arrastrando');
      if (Math.abs(dx) >= UMBRAL_PX) { decidir(t, dx > 0); return; }
      t.style.transform = ''; si.style.opacity = '0'; no.style.opacity = '0';   // vuelve a su sitio
    };
    t.addEventListener('pointerup', soltar);
    t.addEventListener('pointercancel', soltar);
  }

  // Quita las que Python ya no manda y mete por debajo las nuevas (sin tocar las que siguen).
  const quedan = new Set((data.tarjetas || []).map((r) => String(r.id)));
  for (const t of [...mazo.children]) {
    if (!quedan.has(t.dataset.id) && !estado.decididos.has(t.dataset.id)) t.remove();
  }
  const hay = new Set([...mazo.children].map((t) => t.dataset.id));
  for (const r of data.tarjetas || []) {
    const id = String(r.id);
    if (hay.has(id) || estado.decididos.has(id)) continue;
    const t = tarjeta(r, data.base || {});
    arrastrable(t);
    mazo.prepend(t);   // por debajo: la de arriba es la última
  }

  botonNo.onclick = () => decidir(arriba(), false);
  botonSi.onclick = () => decidir(arriba(), true);
  botones();
  parentElement.onkeydown = (e) => {   // con teclado: flechas (en el mapa mueven el mapa)
    if (e.target.closest('.dz-mapa')) return;
    if (e.key === 'ArrowLeft') decidir(arriba(), false);
    if (e.key === 'ArrowRight') decidir(arriba(), true);
  };
}
