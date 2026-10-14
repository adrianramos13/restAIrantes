
export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const lista = parentElement.querySelector('.lr');
  lista.textContent = '';

  data.items.forEach((r) => {
    const li = document.createElement('li');
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'lr-card' + (r.id === data.seleccionado ? ' lr-sel' : '') + (r.cerrado ? ' lr-cerrado' : '')
      + (r.visitado ? ' lr-visitado' : '');
    const partes = [r.amigo ? `${r.amigo} fue ${r.cuando}` : r.cuando, `${r.n}. ${r.nombre}`, r.cocina, r.meta,
      r.nota != null && `${String(r.nota).replace('.', ',')} de 5 estrellas`, r.cita && `«${r.cita}»`,
      r.cerrado, r.visitado && 'Has ido', 'Ver ficha'];
    boton.setAttribute('aria-label', partes.filter(Boolean).join('. '));

    const foto = document.createElement('div');
    foto.className = 'lr-foto';
    const inicial = () => {
      const d = document.createElement('div');
      d.className = 'lr-inicial'; d.textContent = (r.nombre.trim()[0] || '?').toUpperCase();
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
    boton.onclick = () => setTriggerValue('abrir', r.id);
    li.appendChild(boton);
    lista.appendChild(li);
  });
}
