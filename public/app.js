(() => {
  const $ = (s) => document.querySelector(s);
  const form = $('#scan-form'), status = $('#status'), rows = $('#rows'), empty = $('#empty');
  const storedTheme = localStorage.getItem('signalforge-theme');
  const defaultTheme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.dataset.theme = storedTheme || defaultTheme;
  function themeLabel() { $('.theme-toggle').setAttribute('aria-label', `Switch to ${document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'} mode`); }
  themeLabel();
  $('.theme-toggle').addEventListener('click', () => { document.documentElement.dataset.theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; localStorage.setItem('signalforge-theme', document.documentElement.dataset.theme); themeLabel(); });
  let results = [], hasSearched = false;
  function cell(tr, value) { const td = document.createElement('td'); td.textContent = value || '—'; tr.append(td); return td; }
  function render() {
    const term = $('#filter').value.toLowerCase().trim();
    const visible = results.filter(item => Object.values(item).some(value => String(value).toLowerCase().includes(term)));
    rows.replaceChildren();
    for (const item of visible) {
      const tr = document.createElement('tr');
      const first = document.createElement('td'), name = document.createElement('strong'), kind = document.createElement('small');
      name.textContent = item.name || 'Unassigned contact'; kind.textContent = item.kind; first.append(name, kind); tr.append(first);
      cell(tr, [item.role, item.company].filter(Boolean).join(' · ')); cell(tr, item.email); cell(tr, item.phone);
      const source = document.createElement('td'), link = document.createElement('a'); link.href = item.source; link.textContent = 'View source ↗'; link.target = '_blank'; link.rel = 'noopener noreferrer'; source.append(link); tr.append(source); rows.append(tr);
    }
    $('#count').textContent = results.length; $('#toolbar-count').textContent = visible.length;
    $('#export').disabled = !results.length; empty.hidden = visible.length > 0;
    empty.querySelector('strong').textContent = hasSearched ? (results.length ? 'No matching results.' : 'No contacts found on these pages.') : 'Good leads start with a good source.';
    empty.querySelector('p').textContent = hasSearched ? (results.length ? 'Try another filter.' : 'Try another public website or review the scan status.') : 'Your discovered contacts will appear here after a search.';
  }
  $('#filter').addEventListener('input', render);
  form.addEventListener('submit', async (event) => {
    event.preventDefault(); const button = $('#submit'); button.disabled = true; button.firstChild.textContent = 'Searching… '; status.lastElementChild.textContent = 'Checking site rules and scanning pages…';
    try {
      const response = await fetch('/api/scan', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url: $('#url').value, limit: Number($('#limit').value)})});
      const data = await response.json(); if (!response.ok) throw new Error(data.error || 'Search failed.');
      results = data.results; hasSearched = true; $('#filter').value = ''; render();
      status.lastElementChild.textContent = data.warnings.length ? `${data.warnings.join(' ')} ${data.pagesScanned} page(s) attempted.` : `Scan complete · ${data.pagesScanned} page(s) attempted`;
      $('#footnote').textContent = `${data.pagesScanned} page(s) attempted · ${results.length} result(s)`;
    } catch (e) { status.lastElementChild.textContent = `Search stopped: ${e.message}`; }
    finally { button.disabled = false; button.firstChild.textContent = 'Find leads '; }
  });
  $('#export').addEventListener('click', () => {
    const fields=['name','role','company','email','phone','source','kind'];
    const csvCell = value => { let s=String(value ?? ''); if (/^[\s\u0000-\u001f]*[=+\-@]/.test(s)) s="'"+s; return '"'+s.replaceAll('"','""')+'"'; };
    const csv=[fields.map(csvCell).join(','), ...results.map(r=>fields.map(k=>csvCell(r[k])).join(','))].join('\r\n');
    const url=URL.createObjectURL(new Blob(['\ufeff',csv], {type:'text/csv;charset=utf-8'})); const a=document.createElement('a'); a.href=url; a.download='signalforge-leads.csv'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  render();
})();
