(rootSelector) => {
  // Single shared label/description resolver (M25 F1 DD3). Evaluated verbatim
  // by tests/browser/_a11y_resolvers.py (Playwright) and by
  // scripts/webkitgtk_probe.py (WebKitGTK); keep it one self-contained arrow
  // function expression with nothing after the closing brace.
  //
  // Rules, for every control under (and including) each element matching
  // rootSelector:
  //   - control set: input (not hidden), select, textarea, button, a[href],
  //     [role=button], [role=switch], [role=menuitem], [role=option]
  //   - accessible name: labels, aria-label, a resolvable aria-labelledby, or
  //     non-empty text for content-named controls (button, link, menuitem,
  //     option)
  //   - every id in aria-describedby / aria-labelledby must resolve, and an
  //     aria-labelledby target must have non-empty text
  //   - aria-controls must resolve unless the element has aria-expanded=false
  //   - a rootSelector matching nothing is a FAILURE, never a vacuous pass
  const CONTROL_SELECTOR = [
    'input:not([type=hidden])', 'select', 'textarea', 'button', 'a[href]',
    '[role=button]', '[role=switch]', '[role=menuitem]', '[role=option]',
  ].join(',');
  const failures = [];
  let roots;
  try {
    roots = Array.from(document.querySelectorAll(rootSelector));
  } catch (e) {
    return { ok: false, failures: ['invalid root selector ' + JSON.stringify(rootSelector) + ': ' + e.message] };
  }
  if (roots.length === 0) {
    return { ok: false, failures: ['root selector ' + JSON.stringify(rootSelector) + ' matched no element'] };
  }
  const seen = new Set();
  const controls = [];
  roots.forEach((root) => {
    const all = Array.from(root.querySelectorAll(CONTROL_SELECTOR));
    if (root.matches(CONTROL_SELECTOR)) all.unshift(root);
    all.forEach((el) => {
      if (!seen.has(el)) {
        seen.add(el);
        controls.push(el);
      }
    });
  });
  const ids = (value) => (value || '').split(/\s+/).filter(Boolean);
  const text = (el) => (el.textContent || '').replace(/\s+/g, ' ').trim();
  const describe = (el) => {
    let s = '<' + el.tagName.toLowerCase();
    if (el.id) s += '#' + el.id;
    const testid = el.getAttribute('data-testid');
    if (testid) s += ' data-testid=' + testid;
    return s + '> ' + el.outerHTML.slice(0, 80).replace(/\s+/g, ' ');
  };
  const contentNamed = (el) => {
    const role = el.getAttribute('role');
    const tag = el.tagName;
    return tag === 'BUTTON' || tag === 'A' || role === 'button' || role === 'menuitem' || role === 'option';
  };
  controls.forEach((el) => {
    const fail = (rule) => failures.push(describe(el) + ' :: ' + rule);
    const labelledby = ids(el.getAttribute('aria-labelledby'));
    let labelledbyText = false;
    labelledby.forEach((id) => {
      const target = document.getElementById(id);
      if (!target) {
        fail('aria-labelledby references missing id ' + JSON.stringify(id));
      } else if (!text(target)) {
        fail('aria-labelledby target ' + JSON.stringify(id) + ' has empty text');
      } else {
        labelledbyText = true;
      }
    });
    ids(el.getAttribute('aria-describedby')).forEach((id) => {
      if (!document.getElementById(id)) {
        fail('aria-describedby references missing id ' + JSON.stringify(id));
      }
    });
    if (el.getAttribute('aria-expanded') !== 'false') {
      ids(el.getAttribute('aria-controls')).forEach((id) => {
        if (!document.getElementById(id)) {
          fail('aria-controls references missing id ' + JSON.stringify(id));
        }
      });
    }
    let named = false;
    if (el.labels && Array.from(el.labels).some((l) => text(l))) named = true;
    if ((el.getAttribute('aria-label') || '').trim()) named = true;
    if (labelledbyText) named = true;
    if (!named && contentNamed(el) && text(el)) named = true;
    if (!named) fail('control has no accessible name');
  });
  return { ok: failures.length === 0, failures: failures, count: controls.length };
}
