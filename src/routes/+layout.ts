// Aplicación de página única dentro de Tauri: sin renderizado en servidor, y
// todo se prerenderiza contra el `fallback` del adaptador estático.
export const ssr = false;
export const prerender = true;
