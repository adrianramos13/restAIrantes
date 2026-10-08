
const LEAFLET_CSS = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css';
const LEAFLET_JS = 'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js';
const MAPLIBRE_CSS = 'https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.css';
const MAPLIBRE_JS = 'https://cdn.jsdelivr.net/npm/maplibre-gl@5.24.0/dist/maplibre-gl.js';
const PLUGIN_JS = 'https://cdn.jsdelivr.net/npm/@maplibre/maplibre-gl-leaflet@0.1.4/leaflet-maplibre-gl.js';
const TIEMPO_MAX_VECTORIAL_MS = 12000;

function cargarCss(href) {
  return new Promise((ok, fallo) => {
    const l = document.createElement('link');
    l.rel = 'stylesheet'; l.href = href; l.onload = ok; l.onerror = fallo;
    document.head.appendChild(l);
  });
}

function cargarScript(src) {
  return new Promise((ok, fallo) => {
    const sc = document.createElement('script');
    sc.src = src; sc.onload = ok; sc.onerror = fallo;
    document.head.appendChild(sc);
  });
}

function cargarLeaflet() {
  if (window.L && window.L.map) return Promise.resolve(window.L);
  if (!window.__fmLeaflet) {
    window.__fmLeaflet = Promise.all([cargarCss(LEAFLET_CSS), cargarScript(LEAFLET_JS)])
      .then(() => window.L)
      .catch((e) => { window.__fmLeaflet = null; throw e; });
  }
  return window.__fmLeaflet;
}

// MapLibre GL + su plugin para Leaflet (mapa vectorial). Se cargan solo si hacen falta.
function cargarMapLibre() {
  if (window.L && window.L.maplibreGL) return Promise.resolve();
  if (!window.__fmMapLibre) {
    window.__fmMapLibre = Promise.all([
      cargarCss(MAPLIBRE_CSS),
      cargarScript(MAPLIBRE_JS).then(() => cargarScript(PLUGIN_JS)),
    ]).then(() => undefined).catch((e) => { window.__fmMapLibre = null; throw e; });
  }
  return window.__fmMapLibre;
}

function crearPin(r, seleccionado) {
  const pin = document.createElement('div');
  pin.className = 'fm-pin' + (seleccionado ? ' fm-sel' : '') + (r.n === 1 ? ' fm-top' : '');
  const foto = document.createElement('div');
  foto.className = 'fm-foto';
  const sinFoto = () => { foto.textContent = '🍽️'; };
  if (r.foto) {
    const img = document.createElement('img');
    img.alt = ''; img.referrerPolicy = 'no-referrer';
    img.onerror = () => { img.remove(); sinFoto(); };
    img.src = r.foto;
    foto.appendChild(img);
  } else {
    sinFoto();
  }
  const num = document.createElement('span');
  num.className = 'fm-num'; num.textContent = String(r.n);
  const punta = document.createElement('span');
  punta.className = 'fm-punta';
  pin.append(foto, num, punta);
  return pin;
}

function crearPuntoUsuario() {
  const yo = document.createElement('div');
  yo.className = 'fm-yo';
  const pulso = document.createElement('span'); pulso.className = 'fm-yo-pulso';
  const punto = document.createElement('span'); punto.className = 'fm-yo-punto';
  yo.append(pulso, punto);
  return yo;
}

function quitarBase(estado) {
  if (estado.temporizador) { clearTimeout(estado.temporizador); estado.temporizador = null; }
  if (estado.capaBase) { try { estado.capaBase.remove(); } catch (e) { /* ya no estaba */ } estado.capaBase = null; }
  // Restos de una capa vectorial que no llegó a montarse del todo (p. ej. sin WebGL).
  estado.contenedor.querySelectorAll('.leaflet-gl-layer').forEach((el) => el.remove());
}

function ponerRespaldo(L, estado) {
  const r = estado.datos.base.respaldo;
  quitarBase(estado);
  estado.capaBase = L.tileLayer(r.url, { subdomains: r.subdominios, maxZoom: r.maxZoom, attribution: r.atribucion }).addTo(estado.mapa);
  estado.baseClave = 'respaldo';
}

// Mapa vectorial (OpenFreeMap). Si algo falla (sin WebGL, sin red, tarda demasiado) se usa el respaldo.
function ponerVectorial(L, estado) {
  const v = estado.datos.base.vectorial;
  const clave = 'vectorial:' + v.style;
  if (estado.baseClave === clave || estado.baseClave === 'respaldo') return;
  quitarBase(estado);
  estado.baseClave = clave;

  cargarMapLibre().then(() => {
    if (estado.baseClave !== clave || !estado.mapa) return;
    const capa = L.maplibreGL({ style: v.style, attributionControl: { customAttribution: v.atribucion } });
    estado.capaBase = capa;   // antes de añadirla: si addTo falla (p. ej. sin WebGL), quitarBase() puede limpiarla
    capa.addTo(estado.mapa);
    let cargado = false;
    capa.getMaplibreMap().on('styledata', () => { cargado = true; });
    estado.temporizador = setTimeout(() => {
      if (!cargado && estado.baseClave === clave) ponerRespaldo(L, estado);
    }, TIEMPO_MAX_VECTORIAL_MS);
  }).catch(() => {
    if (estado.baseClave === clave) ponerRespaldo(L, estado);
  });
}

function aplicarBase(L, estado) {
  // Limpia capas de mosaicos que no sean las nuestras (p. ej. de una versión anterior con la página abierta).
  estado.mapa.eachLayer((capa) => {
    if (capa instanceof L.TileLayer && capa !== estado.capaBase) capa.remove();
  });
  ponerVectorial(L, estado);
}

function pintar(L, estado) {
  const { usuario, restaurantes, seleccionado } = estado.datos;

  if (!estado.mapa) {
    estado.mapa = L.map(estado.contenedor, { scrollWheelZoom: false });
    estado.capa = L.layerGroup().addTo(estado.mapa);
    // La rueda del ratón solo hace zoom tras pinchar dentro del mapa (así no secuestra el scroll de la página).
    estado.mapa.on('mousedown', () => estado.mapa.scrollWheelZoom.enable());
    estado.contenedor.addEventListener('mouseleave', () => estado.mapa.scrollWheelZoom.disable());
    // Pinchar en un hueco del mapa quita la selección.
    estado.mapa.on('click', () => { if (estado.seleccionado != null) estado.setTrigger('seleccion', -1); });
  }

  aplicarBase(L, estado);

  estado.seleccionado = seleccionado;
  estado.capa.clearLayers();

  L.marker([usuario.lat, usuario.lon], {
    icon: L.divIcon({ className: 'fm-icono', html: crearPuntoUsuario(), iconSize: [22, 22], iconAnchor: [11, 11] }),
    interactive: false, keyboard: false, zIndexOffset: -1000,
  }).addTo(estado.capa);

  restaurantes.forEach((r) => {
    const marcador = L.marker([r.lat, r.lon], {
      icon: L.divIcon({ className: 'fm-icono', html: crearPin(r, r.id === seleccionado), iconSize: [46, 56], iconAnchor: [23, 56] }),
      zIndexOffset: r.id === seleccionado ? 1000 : 100 - r.n,
    });
    const nombre = document.createElement('span');
    nombre.textContent = r.nombre;
    marcador.bindTooltip(nombre, { direction: 'top', offset: [0, -50], opacity: 0.95 });
    marcador.on('click', () => estado.setTrigger('seleccion', r.id));
    marcador.addTo(estado.capa);
  });

  // Encuadre: solo cuando cambia el conjunto de restaurantes (no al seleccionar uno),
  // para no perder el zoom/posición que haya puesto la persona.
  const clave = usuario.lat + ',' + usuario.lon + '|' + restaurantes.map((r) => r.id).join(',');
  if (clave !== estado.clave) {
    estado.clave = clave;
    if (restaurantes.length) {
      const puntos = restaurantes.map((r) => [r.lat, r.lon]).concat([[usuario.lat, usuario.lon]]);
      estado.mapa.fitBounds(L.latLngBounds(puntos), { paddingTopLeft: [40, 75], paddingBottomRight: [40, 35], maxZoom: 16 });
    } else {
      estado.mapa.setView([usuario.lat, usuario.lon], 15);
    }
  }
  estado.mapa.invalidateSize();
}

export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const contenedor = parentElement.querySelector('.fm-mapa');
  if (!contenedor) return;

  // El estado vive en el propio elemento: así sobrevive a las recargas de Streamlit
  // (el JS se vuelve a ejecutar con datos nuevos) sin recrear el mapa ni perder el zoom.
  let estado = contenedor.__fmEstado;
  if (!estado) {
    estado = { contenedor, mapa: null, capa: null, clave: null, seleccionado: null };
    contenedor.__fmEstado = estado;
  }
  estado.setTrigger = setTriggerValue;
  estado.datos = data;

  cargarLeaflet()
    .then((L) => pintar(L, estado))
    .catch(() => {
      contenedor.textContent = '';
      const aviso = document.createElement('div');
      aviso.className = 'fm-mensaje';
      aviso.textContent = 'No se ha podido cargar el mapa. Comprueba tu conexión y recarga la página.';
      contenedor.appendChild(aviso);
    });

  return () => {
    // Solo destruimos el mapa si el elemento ya no está en la página (no en cada recarga).
    setTimeout(() => {
      if (!parentElement.isConnected && estado.mapa) {
        estado.mapa.remove(); estado.mapa = null; contenedor.__fmEstado = null;
      }
    }, 0);
  };
}
