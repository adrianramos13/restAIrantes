// Guarda o borra la cookie de la sesión con contraseña (la lee Python con st.context.cookies al
// cargar la página). Sin HttpOnly porque la pone JavaScript: guarda solo el token de renovación.
export default function (component) {
  const { data } = component;
  if (!data || !data.nombre) return;
  const atributos = `; path=/; SameSite=Lax${location.protocol === 'https:' ? '; Secure' : ''}`;
  if (data.valor) {
    document.cookie = `${data.nombre}=${encodeURIComponent(data.valor)}; max-age=${data.segundos}${atributos}`;
  } else {
    document.cookie = `${data.nombre}=; max-age=0${atributos}`;
  }
}
