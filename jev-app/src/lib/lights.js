// Metadados das luzes de teste e da saude do Hub. Modulo puro, sem DOM.
// `icon` e o nome do icone lucide; `tone` e a chave do tema (--color-light-*).

export const LIGHTS = ['green', 'yellow', 'red', 'grey'];

const LIGHT_META = {
  green: { label: 'Verde', icon: 'CircleCheck', tone: 'green' },
  yellow: { label: 'Amarela', icon: 'TriangleAlert', tone: 'yellow' },
  red: { label: 'Vermelha', icon: 'CircleX', tone: 'red' },
  grey: { label: 'Cinza', icon: 'CircleHelp', tone: 'grey' },
};

const HEALTH_META = {
  green: { label: 'Saudável', icon: 'HeartPulse', tone: 'green' },
  yellow: { label: 'Degradada', icon: 'TriangleAlert', tone: 'yellow' },
  red: { label: 'Com falha', icon: 'CircleX', tone: 'red' },
  unknown: { label: 'Desconhecida', icon: 'CircleHelp', tone: 'grey' },
};

const has = (table, key) => typeof key === 'string' && Object.prototype.hasOwnProperty.call(table, key);

export function lightMeta(light) {
  return { ...(has(LIGHT_META, light) ? LIGHT_META[light] : LIGHT_META.grey) };
}

export function healthMeta(status) {
  return { ...(has(HEALTH_META, status) ? HEALTH_META[status] : HEALTH_META.unknown) };
}
