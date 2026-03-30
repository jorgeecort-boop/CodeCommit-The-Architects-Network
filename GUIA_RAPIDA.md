# Guia Rapida CodeCommit v2.5

## 1) Crear cuenta o iniciar sesion
- Abre `http://localhost:8080`.
- Si eres nuevo, usa `Register` con tu `username`, `password`, `stack`, `years_exp` y preferencias.
- Si ya tienes cuenta, entra por `Login`.

## 2) Mantener sesion activa
- La app guarda tu token JWT en el navegador para que no tengas que loguearte en cada recarga.
- Para cerrar sesion, usa el boton `Cerrar sesion`.

## 3) Subir foto de setup y avatar
- En la app/API puedes subir imagenes en `png`, `jpg/jpeg` o `webp` (max 5MB).
- Endpoints: `POST /v2/me/avatar` y `POST /v2/me/setup`.
- Las imagenes se guardan en `./data/media` y se sirven desde `/media/...`.

## 4) Hacer tu primer Pull Request (Like)
- En el feed, pulsa `Pull Request` en el perfil que te interese.
- Si la otra persona te envia PR de vuelta, se genera match automatico y se abre chat.
- Si no hay PR reciproco, queda pendiente hasta que esa persona haga `Merge`.

## 5) Abrir chat realtime (primer Merge)
- Cuando haya match, se crea un chat y los mensajes llegan en tiempo real (WebSocket) sin refrescar.
- Puedes ver historial y enviar mensajes desde la ventana de chat.
