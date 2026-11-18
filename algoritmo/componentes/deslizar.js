// «Food match»: pila de tarjetas. Arrastrar a la derecha (o ♥) = me gusta; a la izquierda (o ✕) = no.
// Python manda las tarjetas pendientes (data.tarjetas, la primera es la de arriba) y recibe cada decisión por el
// trigger «decision» = {id, gusta}. La pila vive aquí: las tarjetas nuevas se meten por debajo sin redibujar las
// que ya están, así que no hay parpadeos mientras Python guarda y manda la siguiente tanda.
const UMBRAL_PX = 100;   // lo que hay que arrastrar para que cuente
const TOQUE_PX = 8;      // moverse menos que esto al soltar = tocar la foto (pasa a la siguiente)
const ANADIDO_MS = 4000; // lo que dura el aviso «Añadido a tu lista» (y la barrita .dz-anadido-tiempo de deslizar.css)
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

// Fotos de la tarjeta: las de su galería (r.fotos) o, si aún no tiene, la de siempre (r.foto). Se ve una; tocarla
// pasa a la siguiente (el tercio izquierdo, a la anterior) y las rayitas de arriba dicen en cuál estás.
function fotos(t, r) {
  const urls = r.fotos && r.fotos.length ? r.fotos : (r.foto ? [r.foto] : []);
  if (!urls.length) { t.append(inicial(r.nombre)); return; }
  t.append(...urls.map((url, i) => {
    const img = document.createElement('img');
    img.className = 'dz-foto'; img.alt = ''; img.draggable = false; img.hidden = i > 0;
    if (i === 0) img.src = url; else img.dataset.src = url;   // la primera ya; el resto, al llegar arriba (cargarFotos)
    img.onerror = () => quitarFoto(t, img, r.nombre);
    return img;
  }), texto('div', 'dz-barras', ''));
  pintarBarras(t);
}

const fotosDe = (t) => [...t.querySelectorAll('.dz-foto')];

function pintarBarras(t) {
  const imgs = fotosDe(t), actual = imgs.findIndex((img) => !img.hidden);
  const barras = t.querySelector('.dz-barras');
  barras.replaceChildren(...(imgs.length > 1 ? imgs.map((img, i) => texto('span', i === actual ? 'dz-actual' : '', '')) : []));
  barras.setAttribute('aria-label', imgs.length > 1 ? `Foto ${actual + 1} de ${imgs.length}` : '');
}

function cargarFotos(t) {
  for (const img of t.querySelectorAll('.dz-foto[data-src]')) { img.src = img.dataset.src; delete img.dataset.src; }
}

function mostrarFoto(t, paso) {
  const imgs = fotosDe(t);
  if (imgs.length < 2) return;
  const siguiente = (imgs.findIndex((img) => !img.hidden) + paso + imgs.length) % imgs.length;
  imgs.forEach((img, i) => { img.hidden = i !== siguiente; });
  pintarBarras(t);
}

function quitarFoto(t, img, nombre) {   // no carga: fuera, y si era la que se veía, se enseña otra
  const seVeia = !img.hidden;
  img.remove();
  const imgs = fotosDe(t);
  if (!imgs.length) { t.querySelector('.dz-barras').remove(); t.prepend(inicial(nombre)); return; }
  if (seVeia) imgs[0].hidden = false;
  pintarBarras(t);
}

function tarjeta(r, base) {
  const t = document.createElement('div');
  t.className = 'dz-tarjeta';
  t.dataset.id = String(r.id);
  t.__datos = r;
  t.setAttribute('role', 'group');
  t.setAttribute('aria-label', r.nombre);
  fotos(t, r);
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

// Foto de perfil de un amigo (o su inicial sobre su color) con su @usuario debajo
function perfil(p, i) {
  const caja = texto('div', 'dz-perfil', '');
  caja.style.animationDelay = `${0.35 + i * 0.15}s`;
  const circulo = texto('span', 'dz-avatar', p.inicial || '?');
  circulo.style.background = p.color || '#888';
  if (p.foto) {
    const img = Object.assign(document.createElement('img'), { alt: '', referrerPolicy: 'no-referrer', src: p.foto });
    img.onerror = () => img.remove();
    circulo.append(img);
  }
  caja.append(circulo, texto('span', 'dz-perfil-nombre', p.nombre || ''));
  return caja;
}

// Al dar «me gusta»: la tarjeta del restaurante, «Añadido a tu lista» y, si algún amigo también lo tiene en su lista,
// «Tienes el mismo gusto que» con dos perfiles como mucho (+X el resto). Se va sola a los ANADIDO_MS o al tocarla.
function mostrarAnadido(r) {
  document.querySelector('.dz-anadido')?.remove();
  const capa = texto('div', 'dz-anadido', '');
  capa.setAttribute('role', 'status');
  const caja = texto('div', 'dz-anadido-caja', '');
  const marco = texto('div', 'dz-anadido-tarjeta', '');
  const t = tarjeta({ ...r, lat: null, lon: null }, {});   // la misma tarjeta, sin mapa ni arrastre
  marco.append(t);
  cargarFotos(t);
  caja.append(marco, texto('div', 'dz-anadido-ok', '✓ Añadido a tu lista'));
  const gusto = r.gusto;
  if (gusto && gusto.perfiles && gusto.perfiles.length) {
    const bloque = texto('div', 'dz-gusto', '');
    const titulo = texto('div', 'dz-gusto-titulo', 'Tienes el mismo gusto que');
    titulo.prepend(texto('span', 'dz-latido', '❤'));
    const fila = texto('div', 'dz-gusto-perfiles', '');
    gusto.perfiles.forEach((p, i) => fila.append(perfil(p, i)));
    if (gusto.mas > 0) {
      const mas = texto('div', 'dz-perfil', '');
      mas.style.animationDelay = `${0.35 + gusto.perfiles.length * 0.15}s`;
      mas.append(texto('span', 'dz-avatar dz-mas', `+${gusto.mas}`));
      mas.setAttribute('aria-label', `y ${gusto.mas} más`);
      fila.append(mas);
    }
    bloque.append(titulo, fila);
    caja.append(bloque);
  }
  caja.append(texto('div', 'dz-anadido-tiempo', ''));
  capa.append(caja);
  const cerrar = () => capa.remove();
  capa.addEventListener('click', cerrar);
  setTimeout(cerrar, ANADIDO_MS);
  document.body.append(capa);   // fuera del mazo: no le afecta que llegue una tanda nueva
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
    [...mazo.children].filter((t) => !estado.decididos.has(t.dataset.id)).slice(-2)
      .forEach((t) => { prepararMapa(t); cargarFotos(t); });
  };

  function decidir(t, gusta) {
    if (!t || estado.decididos.has(t.dataset.id)) return;
    estado.decididos.add(t.dataset.id);
    t.style.transform = `translateX(${gusta ? 150 : -150}%) rotate(${gusta ? 25 : -25}deg)`;
    t.style.opacity = '0';
    setTimeout(() => { if (t.__mapa) t.__mapa.remove(); t.remove(); }, 260);
    botones();
    setTriggerValue('decision', { id: Number(t.dataset.id), gusta });
    if (gusta) mostrarAnadido(t.__datos);
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
    const soltar = (e) => {
      if (x0 === null) return;
      x0 = null;
      t.classList.remove('dz-arrastrando');
      if (Math.abs(dx) >= UMBRAL_PX) { decidir(t, dx > 0); return; }
      t.style.transform = ''; si.style.opacity = '0'; no.style.opacity = '0';   // vuelve a su sitio
      if (e.type === 'pointerup' && Math.abs(dx) < TOQUE_PX) {   // un toque, no un arrastre: cambia de foto
        const caja = t.getBoundingClientRect();
        mostrarFoto(t, e.clientX - caja.left < caja.width / 3 ? -1 : 1);
      }
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
