import { describe, expect, it } from 'vitest';

import { accionDeTecla, type Tecla } from './atajos';

const t = (key: string, extra: Partial<Tecla> = {}): Tecla => ({
  key,
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  escribiendo: false,
  ...extra
});

describe('los atajos de la V1', () => {
  it('traducen cada tecla a su acción', () => {
    expect(accionDeTecla(t(' '))).toBe('pausarReanudar');
    expect(accionDeTecla(t('ArrowUp'))).toBe('anterior');
    expect(accionDeTecla(t('S'))).toBe('aleatorio');
    expect(accionDeTecla(t('q', { ctrlKey: true }))).toBe('cola');
    expect(accionDeTecla(t('m', { metaKey: true }))).toBe('mini');
  });

  it('no actúan mientras se escribe, salvo los de Ctrl', () => {
    expect(accionDeTecla(t(' ', { escribiendo: true }))).toBeNull();
    expect(accionDeTecla(t('s', { escribiendo: true }))).toBeNull();
    expect(accionDeTecla(t('q', { ctrlKey: true, escribiendo: true }))).toBe('cola');
  });

  it('dejan en paz lo demás', () => {
    expect(accionDeTecla(t('x'))).toBeNull();
    expect(accionDeTecla(t('s', { altKey: true }))).toBeNull();
    expect(accionDeTecla(t('k', { ctrlKey: true }))).toBeNull();
  });
});
