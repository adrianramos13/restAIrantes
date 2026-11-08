
function span(clase, texto) {
  const s = document.createElement('span'); s.className = clase; s.textContent = texto;
  return s;
}

// Póster ("Lo mejor de la semana"): la foto ocupa la tarjeta y encima, abajo, tres barras alargadas:
// el sitio (nota y precio de Google), quién fue con sus estrellas y su comentario (si dejó).
function barrasPoster(r) {
  const barras = document.createElement('div'); barras.className = 'lr-barras';
  const sitio = document.createElement('div'); sitio.className = 'lr-barra';
  sitio.append(span('lr-nombre', r.nombre), span('lr-meta', r.meta));
  const quien = document.createElement('div'); quien.className = 'lr-barra lr-barra-quien';
  const persona = span('lr-quien', '');
  persona.append(span('lr-amigo', r.amigo || ''), span('lr-cuando', r.cuando || ''));
  quien.append(persona);
  if (r.nota != null) {
    const estrellas = span('lr-estrellas', ''); estrellas.setAttribute('aria-hidden', 'true');
    const dibujo = span('lr-e-dibujo', '');
    const relleno = span('lr-e-relleno', '★★★★★'); relleno.style.width = `${(r.nota / 5) * 100}%`;
    dibujo.append(span('lr-e-fondo', '★★★★★'), relleno);
    estrellas.append(dibujo, span('lr-e-numero', String(r.nota).replace('.', ',')));
    quien.append(estrellas);
  }
  barras.append(sitio, quien);
  if (r.cita) {
    const cita = document.createElement('div'); cita.className = 'lr-barra';
    cita.append(span('lr-cita', `«${r.cita}»`));
    barras.append(cita);
  }
  return barras;
}

export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const lista = parentElement.querySelector('.lr');
  lista.textContent = '';
  lista.classList.toggle('lr-carrusel', !!data.carrusel);   // tarjetas pequeñas en una fila que se desliza
  lista.classList.toggle('lr-posters', !!data.poster);

  data.items.forEach((r) => {
    const li = document.createElement('li');
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'lr-card' + (r.id === data.seleccionado ? ' lr-sel' : '') + (r.cerrado ? ' lr-cerrado' : '')
      + (r.visitado ? ' lr-visitado' : '');
    const partes = [r.amigo ? `${r.amigo} fue ${r.cuando}` : r.cuando, `${r.n}. ${r.nombre}`, r.cocina, r.meta,
      r.nota != null && `${String(r.nota).replace('.', ',')} de 5 estrellas`, r.cita && `«${r.cita}»`,
      r.estado_texto, r.cerrado, r.visitado && 'Has ido', 'Ver ficha'];
    boton.setAttribute('aria-label', partes.filter(Boolean).join('. '));

    const foto = document.createElement('div');
    foto.className = 'lr-foto';
    const inicial = () => {
      const d = document.createElement('div');
      d.className = 'lr-inicial'; d.textContent = (r.nombre.trim()[0] || '?').toUpperCase();
      if (r.icono) { d.classList.add('lr-icono'); d.textContent = r.icono; }   // Explorar: según la cocina
      return d;
    };
    if (r.foto) {
      const img = document.createElement('img');
      img.alt = ''; img.loading = 'lazy'; img.referrerPolicy = 'no-referrer'; img.src = r.foto;
      img.onerror = () => img.replaceWith(inicial());
      foto.appendChild(img);
    } else {
      foto.appendChild(inicial());
    }
    const num = document.createElement('span');
    num.className = 'lr-num'; num.textContent = String(r.n);
    foto.appendChild(num);
    if (data.poster) {
      boton.append(foto, barrasPoster(r));
      boton.onclick = () => setTriggerValue('abrir', r.id);
      li.appendChild(boton);
      lista.appendChild(li);
      return;
    }

    const info = document.createElement('div');
    info.className = 'lr-info';
    if (r.amigo || r.cuando) {   // quién fue (bien visible) y cuándo (que nunca se corta)
      const quien = document.createElement('span'); quien.className = 'lr-quien';
      if (r.amigo) {
        const amigo = document.createElement('strong'); amigo.className = 'lr-amigo'; amigo.textContent = r.amigo;
        quien.appendChild(amigo);
      }
      const cuando = document.createElement('span'); cuando.className = 'lr-cuando'; cuando.textContent = r.cuando || '';
      quien.appendChild(cuando);
      info.appendChild(quien);
    }
    const nombre = document.createElement('span'); nombre.className = 'lr-nombre'; nombre.textContent = r.nombre;
    const cocina = document.createElement('span'); cocina.className = 'lr-cocina'; cocina.textContent = r.cocina;
    const meta = document.createElement('span'); meta.className = 'lr-meta'; meta.textContent = r.meta;
    info.append(nombre, cocina, meta);
    if (r.nota != null) {   // estrellas en su propia línea: no se cortan aunque el nombre sea largo
      const estrellas = document.createElement('span'); estrellas.className = 'lr-estrellas';
      estrellas.setAttribute('aria-hidden', 'true');
      const fondo = document.createElement('span'); fondo.className = 'lr-e-fondo'; fondo.textContent = '★★★★★';
      const relleno = document.createElement('span'); relleno.className = 'lr-e-relleno'; relleno.textContent = '★★★★★';
      relleno.style.width = `${(r.nota / 5) * 100}%`;
      const numero = document.createElement('span'); numero.className = 'lr-e-numero';
      numero.textContent = String(r.nota).replace('.', ',');
      const dibujo = document.createElement('span'); dibujo.className = 'lr-e-dibujo';
      dibujo.append(fondo, relleno);
      estrellas.append(dibujo, numero);
      info.appendChild(estrellas);
    }
    if (r.cita) {
      const cita = document.createElement('span'); cita.className = 'lr-cita'; cita.textContent = `«${r.cita}»`;
      info.appendChild(cita);
    }
    if (r.estado_texto) {   // Explorar: analizado / analizando / datos básicos
      const estado = document.createElement('span');
      estado.className = `lr-etiqueta lr-estado-${r.estado}`; estado.textContent = r.estado_texto;
      info.appendChild(estado);
    }
    if (r.visitado) {
      const ido = document.createElement('span'); ido.className = 'lr-etiqueta lr-ido'; ido.textContent = '✓ Has ido';
      info.appendChild(ido);
    }
    if (r.cerrado) {
      const etiqueta = document.createElement('span'); etiqueta.className = 'lr-etiqueta'; etiqueta.textContent = r.cerrado;
      info.appendChild(etiqueta);
    }

    const flecha = document.createElement('span');
    flecha.className = 'lr-flecha'; flecha.setAttribute('aria-hidden', 'true'); flecha.textContent = '›';

    boton.append(foto, info, flecha);
    if (data.estatica) {   // solo para mirar (p. ej. dentro del mini perfil de un amigo): no abre la ficha
      boton.disabled = true; boton.classList.add('lr-estatica'); flecha.hidden = true;
    } else {
      boton.onclick = () => setTriggerValue('abrir', r.id);
    }
    li.appendChild(boton);
    lista.appendChild(li);
  });
}
