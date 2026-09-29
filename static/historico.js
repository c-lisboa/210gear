(function () {
  const MAX = 8;
  const pag = location.pathname;
  const CHAVE = pag.startsWith('/voo') ? 'hist_voo'
              : pag.startsWith('/busca') ? 'hist_busca' : null;
  if (!CHAVE) return;

  const ler = () => { try { return JSON.parse(localStorage.getItem(CHAVE)) || []; } catch { return []; } };
  const gravar = l => localStorage.setItem(CHAVE, JSON.stringify(l.slice(0, MAX)));

  function salvar(t) {
    t = (t || '').trim().toUpperCase();
    if (!t) return;
    gravar([t, ...ler().filter(x => x !== t)]);
    desenhar();
  }
  function remover(t) { gravar(ler().filter(x => x !== t)); desenhar(); }
  function limpar() { localStorage.removeItem(CHAVE); desenhar(); }

  // 🛫 Página /voo: guarda só os voos que foram encontrados
  if (CHAVE === 'hist_voo') {
    const fetchOriginal = window.fetch;
    window.fetch = async function (...args) {
      const resp = await fetchOriginal.apply(this, args);
      try {
        const url = String(args[0] && args[0].url || args[0]);
        const m = url.match(/\/api\/voo\/([^/?#]+)/);
        if (m) resp.clone().json().then(d => { if (d && !d.erro) salvar(decodeURIComponent(m[1])); }).catch(() => {});
      } catch {}
      return resp;
    };
  }

  let caixa, campo;

  function usar(t) {
    if (CHAVE === 'hist_busca') { location.href = '/busca?q=' + encodeURIComponent(t); return; }
    if (!campo) return;
    campo.value = t;
    campo.dispatchEvent(new Event('input', { bubbles: true }));
    if (campo.form) { campo.form.requestSubmit(); return; }
    const botao = campo.parentElement.querySelector('button') || document.querySelector('main button');
    if (botao) botao.click();
    else campo.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  }

  function desenhar() {
    if (!caixa) return;
    const lista = ler();
    if (!lista.length) { caixa.style.display = 'none'; return; }
    caixa.style.display = 'block';
    caixa.innerHTML = '<span class="hist-titulo">🕘 Buscas recentes:</span>';
    lista.forEach(t => {
      const chip = document.createElement('span');
      chip.className = 'hist-chip';
      chip.innerHTML = `<b></b><i title="Remover">✕</i>`;
      chip.querySelector('b').textContent = t;
      chip.querySelector('b').onclick = () => usar(t);
      chip.querySelector('i').onclick = () => remover(t);
      caixa.appendChild(chip);
    });
    const lim = document.createElement('a');
    lim.className = 'hist-limpar'; lim.textContent = '🗑️ Limpar';
    lim.onclick = limpar;
    caixa.appendChild(lim);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const css = document.createElement('style');
    css.textContent = `
      #historico{margin:10px 0 16px;font-size:14px}
      .hist-titulo{margin-right:6px;color:#7f8c8d}
      .hist-chip{display:inline-flex;gap:6px;align-items:center;background:#1a3a5a;color:#fff;
        border-radius:16px;padding:4px 10px;margin:3px;cursor:pointer}
      .hist-chip i{font-style:normal;opacity:.6}
      .hist-chip i:hover{opacity:1;color:#e74c3c}
      .hist-limpar{margin-left:8px;cursor:pointer;color:#c0392b;font-size:13px}`;
    document.head.appendChild(css);

    campo = document.querySelector('main input[type=text], main input[type=search], main input:not([type])');
    caixa = document.createElement('div');
    caixa.id = 'historico';
    const ancora = campo ? (campo.form || campo.parentElement) : null;
    if (ancora) ancora.insertAdjacentElement('afterend', caixa);
    else document.querySelector('main').prepend(caixa);

    // 🔎 Página /busca: guarda o termo pesquisado
    if (CHAVE === 'hist_busca') {
      const q = new URLSearchParams(location.search).get('q');
      if (q) salvar(q);
    }
    desenhar();
  });
})();
