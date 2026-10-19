// Tu foto de perfil: al tocarla se abre el selector del móvil (galería o cámara). La foto elegida se recorta en
// cuadrado y se reduce aquí (máx. 512 px, JPEG) para que suba rápido; Python la vuelve a comprobar y limpiar.
const LADO_MAX = 512;

async function cuadrada(archivo) {
  let bmp;
  try {
    bmp = await createImageBitmap(archivo, { imageOrientation: 'from-image' });   // respeta el giro del móvil
  } catch (e) {
    bmp = await createImageBitmap(archivo);   // navegadores sin esa opción
  }
  const lado = Math.min(bmp.width, bmp.height);
  const destino = Math.min(LADO_MAX, lado);
  const lienzo = document.createElement('canvas');
  lienzo.width = destino; lienzo.height = destino;
  lienzo.getContext('2d').drawImage(bmp, (bmp.width - lado) / 2, (bmp.height - lado) / 2, lado, lado, 0, 0, destino, destino);
  return lienzo.toDataURL('image/jpeg', 0.9);
}

export default function (component) {
  const { parentElement, data, setTriggerValue } = component;
  const caja = parentElement.querySelector('.avatar-perfil');
  const boton = parentElement.querySelector('.cambiar');
  const circulo = parentElement.querySelector('.circulo');
  const inicial = parentElement.querySelector('.inicial');
  const img = parentElement.querySelector('img');
  const input = parentElement.querySelector('input');

  caja.classList.remove('subiendo');   // cada vez que se dibuja de nuevo (p. ej. con la foto ya subida)
  circulo.style.background = data.color;
  inicial.textContent = data.inicial || '?';
  if (data.foto) {
    img.onerror = () => { img.hidden = true; };
    img.src = data.foto;
    img.hidden = false;
  } else {
    img.hidden = true;
  }

  boton.onclick = () => input.click();
  input.onchange = async () => {
    const archivo = input.files && input.files[0];
    input.value = '';
    if (!archivo) return;
    caja.classList.add('subiendo');
    try {
      setTriggerValue('foto', await cuadrada(archivo));
    } catch (e) {
      caja.classList.remove('subiendo');
      setTriggerValue('error', 'no_es_imagen');
    }
  };
}
