import '../../../src/fuentes.css';
import '../../../src/app.css';

import { mount } from 'svelte';

import Banco from './Banco.svelte';

mount(Banco, { target: document.getElementById('app') as HTMLElement });
