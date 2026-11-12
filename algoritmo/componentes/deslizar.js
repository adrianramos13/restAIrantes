// «Food match»: pila de tarjetas. Arrastrar a la derecha (o ♥) = me gusta; a la izquierda (o ✕) = no.
// Python manda las tarjetas pendientes (data.tarjetas, la primera es la de arriba) y recibe cada decisión por el
// trigger «decision» = {id, gusta}. La pila vive aquí: las tarjetas nuevas se meten por debajo sin redibujar las
// que ya están, así que no hay parpadeos mientras Python guarda y manda la siguiente tanda.
const UMBRAL_PX = 100;   // lo que hay que arrastrar para que cuente

function texto(etiqueta, clase, contenido) {
  const e = document.createElement(etiqueta); e.className = clase; e.textContent = contenido;
  return e;
}

function inicial(nombre) {
  return texto('div', 'dz-sin-foto', (nombre || '?').trim().charAt(0).toUpperCase());
}

function tarjeta(r) {
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
  const info = document.createElement('div'); info.className = 'dz-info';
  info.append(texto('div', 'dz-nombre', r.nombre));
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
  const botones = () => { botonNo.disabled = botonSi.disabled = !arriba(); };

  function decidir(t, gusta) {
    if (!t || estado.decididos.has(t.dataset.id)) return;
    estado.decididos.add(t.dataset.id);
    t.style.transform = `translateX(${gusta ? 150 : -150}%) rotate(${gusta ? 25 : -25}deg)`;
    t.style.opacity = '0';
    setTimeout(() => t.remove(), 260);
    botones();
    setTriggerValue('decision', { id: Number(t.dataset.id), gusta });
  }

  function arrastrable(t) {
    let x0 = null, dx = 0;
    const si = t.querySelector('.dz-sello-si'), no = t.querySelector('.dz-sello-no');
    t.addEventListener('pointerdown', (e) => {
      if (t !== arriba()) return;
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
    const t = tarjeta(r);
    arrastrable(t);
    mazo.prepend(t);   // por debajo: la de arriba es la última
  }

  botonNo.onclick = () => decidir(arriba(), false);
  botonSi.onclick = () => decidir(arriba(), true);
  botones();
  parentElement.onkeydown = (e) => {   // con teclado: flechas
    if (e.key === 'ArrowLeft') decidir(arriba(), false);
    if (e.key === 'ArrowRight') decidir(arriba(), true);
  };
}
