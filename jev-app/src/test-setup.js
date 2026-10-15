// Setup do vitest: jsdom nao implementa showModal/close de <dialog>; limpeza do DOM entre testes.
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

if (typeof HTMLDialogElement !== 'undefined') {
  const proto = HTMLDialogElement.prototype;
  proto.showModal = function showModal() {
    this.setAttribute('open', '');
  };
  proto.show = function show() {
    this.setAttribute('open', '');
  };
  proto.close = function close(returnValue) {
    if (!this.hasAttribute('open')) return;
    this.removeAttribute('open');
    if (returnValue !== undefined) this.returnValue = returnValue;
    this.dispatchEvent(new Event('close'));
  };
}

afterEach(() => cleanup());
