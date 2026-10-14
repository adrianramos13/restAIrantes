// Nota de 0,5 a 5 en medias estrellas. Se guarda como "estado" del componente (Python lo lee con
// st.session_state[key].nota). Con el teclado: flechas, de media en media.
export default function (component) {
  const { parentElement, data, setStateValue } = component;
  const caja = parentElement.querySelector('.valorar');
  const relleno = parentElement.querySelector('.relleno');
  const texto = parentElement.querySelector('.texto');
  let valor = data.valor ?? null;

  const pintar = (v) => {
    relleno.style.width = `${((v || 0) / 5) * 100}%`;
    caja.setAttribute('aria-valuenow', String(v || 0));
    caja.setAttribute('aria-valuetext', v ? `${String(v).replace('.', ',')} de 5 estrellas` : 'Sin nota');
    texto.textContent = v ? `${String(v).replace('.', ',')} / 5` : 'Toca para puntuar';
  };
  const desdeX = (x) => {
    const r = caja.getBoundingClientRect();
    return Math.min(5, Math.max(0.5, Math.ceil(((x - r.left) / r.width) * 10) / 2));
  };
  const elegir = (v) => { valor = v; pintar(v); setStateValue('nota', v); };

  caja.onpointermove = (e) => { if (e.pointerType === 'mouse') pintar(desdeX(e.clientX)); };
  caja.onpointerleave = () => pintar(valor);
  caja.onclick = (e) => elegir(desdeX(e.clientX));
  caja.onkeydown = (e) => {
    const paso = { ArrowRight: 0.5, ArrowUp: 0.5, ArrowLeft: -0.5, ArrowDown: -0.5 }[e.key];
    if (paso) { e.preventDefault(); elegir(Math.min(5, Math.max(0.5, (valor || 0) + paso))); }
  };
  pintar(valor);
}
