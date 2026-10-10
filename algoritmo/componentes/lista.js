
export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const lista = parentElement.querySelector('.lr');
  lista.textContent = '';

  data.items.forEach((r) => {
    const li = document.createElement('li');
    const boton = document.createElement('button');
    boton.type = 'button';
    boton.className = 'lr-card' + (r.id === data.seleccionado ? ' lr-sel' : '') + (r.cerrado ? ' lr-cerrado' : '');
    boton.setAttribute('aria-label', `${r.n}. ${r.nombre}. ${r.cocina}. ${r.meta}${r.cerrado ? '. ' + r.cerrado : ''}. Ver ficha`);

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
    const nombre = document.createElement('span'); nombre.className = 'lr-nombre'; nombre.textContent = r.nombre;
    const cocina = document.createElement('span'); cocina.className = 'lr-cocina'; cocina.textContent = r.cocina;
    const meta = document.createElement('span'); meta.className = 'lr-meta'; meta.textContent = r.meta;
    info.append(nombre, cocina, meta);
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
