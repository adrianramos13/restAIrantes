
export default function (component) {
  const { parentElement, setTriggerValue } = component;
  const boton = parentElement.querySelector('#boton');
  const etiqueta = boton.querySelector('.etiqueta');
  const textoNormal = 'Usar mi ubicación';

  boton.onclick = () => {
    if (!navigator.geolocation) { setTriggerValue('error', 'no_soportado'); return; }
    boton.disabled = true;
    etiqueta.textContent = 'Buscando tu ubicación…';
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        boton.disabled = false; etiqueta.textContent = textoNormal;
        setTriggerValue('ubicacion', {
          lat: pos.coords.latitude, lon: pos.coords.longitude, precision: pos.coords.accuracy,
        });
      },
      (err) => {
        boton.disabled = false; etiqueta.textContent = textoNormal;
        setTriggerValue('error', String(err.code));  // 1 denegado, 2 no disponible, 3 tiempo agotado
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 }
    );
  };
}
