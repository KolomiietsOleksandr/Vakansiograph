/* ════════ Scrolled header state ═════════════════════════════════ */
(function scrolledHeader() {
  const h = document.getElementById('main-header');
  if (!h) return;
  const onScroll = () => h.classList.toggle('scrolled', window.scrollY > 6);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
})();

/* ════════ Scroll reveal ═════════════════════════════════════════ */
(function scrollReveal() {
  const items = document.querySelectorAll('.reveal, .reveal-left, .reveal-right, .reveal-scale');
  if (!items.length) return;
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('in');
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
  items.forEach(el => io.observe(el));
})();

/* ════════ Animated counter ══════════════════════════════════════ */
window.animateCounter = function (el, target, opts = {}) {
  if (!el) return;
  const duration = opts.duration || 1400;
  const prefix = opts.prefix || el.dataset.prefix || '';
  const suffix = opts.suffix || el.dataset.suffix || '';
  const formatter = opts.formatter || (v => Math.round(v).toLocaleString());
  const start = performance.now();
  function step(now) {
    const p = Math.min(1, (now - start) / duration);
    const ease = p === 1 ? 1 : 1 - Math.pow(2, -10 * p);
    el.textContent = prefix + formatter(ease * target) + suffix;
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
};

/* ════════ Live ticker ═══════════════════════════════════════════ */
window.startTicker = function (containerId, items) {
  const container = document.getElementById(containerId);
  if (!container || !items.length) return;
  let idx = 0;
  container.innerHTML = items.map((it, i) =>
    `<div class="ticker-item${i === 0 ? ' active' : ''}" data-i="${i}">${it}</div>`
  ).join('');
  const els = container.querySelectorAll('.ticker-item');
  setInterval(() => {
    const cur = els[idx];
    const nextIdx = (idx + 1) % els.length;
    const next = els[nextIdx];
    cur.classList.remove('active');
    cur.classList.add('out');
    setTimeout(() => cur.classList.remove('out'), 500);
    next.classList.add('active');
    idx = nextIdx;
  }, 2400);
};
