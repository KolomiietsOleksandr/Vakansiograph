(function () {
  const canvas = document.getElementById('heroCanvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  const DPR = Math.min(window.devicePixelRatio || 1, 2);

  let w = 0, h = 0;
  let particles = [];
  let mouse = { x: -9999, y: -9999, active: false };
  let t = 0;

  // ─── Sized to parent
  function resize() {
    const rect = canvas.parentElement.getBoundingClientRect();
    w = rect.width;
    h = rect.height;
    canvas.width = w * DPR;
    canvas.height = h * DPR;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    initParticles();
  }

  // ─── World map dots (rough US/Europe/Asia silhouette)
  // Plotted as relative coords [0..1] over canvas
  const mapDots = generateMapDots();
  function generateMapDots() {
    const dots = [];
    // North America
    for (let i = 0; i < 110; i++) {
      const x = 0.10 + Math.random() * 0.18;
      const y = 0.30 + Math.random() * 0.28;
      // bias toward continental US shape
      if (Math.random() < 0.7 && y > 0.42 && y < 0.5 && x > 0.15 && x < 0.26) dots.push([x, y]);
      else if (Math.random() < 0.5) dots.push([x, y]);
    }
    // Europe
    for (let i = 0; i < 70; i++) {
      const x = 0.42 + Math.random() * 0.10;
      const y = 0.30 + Math.random() * 0.18;
      dots.push([x, y]);
    }
    // Asia
    for (let i = 0; i < 90; i++) {
      const x = 0.55 + Math.random() * 0.25;
      const y = 0.32 + Math.random() * 0.22;
      dots.push([x, y]);
    }
    // South America
    for (let i = 0; i < 35; i++) {
      const x = 0.22 + Math.random() * 0.08;
      const y = 0.55 + Math.random() * 0.20;
      dots.push([x, y]);
    }
    // Africa
    for (let i = 0; i < 55; i++) {
      const x = 0.42 + Math.random() * 0.10;
      const y = 0.48 + Math.random() * 0.25;
      dots.push([x, y]);
    }
    // Australia
    for (let i = 0; i < 30; i++) {
      const x = 0.74 + Math.random() * 0.08;
      const y = 0.65 + Math.random() * 0.10;
      dots.push([x, y]);
    }
    // hotspots — bigger pulse dots
    return dots.map(([x, y]) => ({
      x, y,
      r: Math.random() < 0.06 ? 2.4 : 1.0 + Math.random() * 0.6,
      hot: Math.random() < 0.06,
      phase: Math.random() * Math.PI * 2,
      speed: 0.6 + Math.random() * 1.2
    }));
  }

  // ─── Particle network
  function initParticles() {
    const count = Math.min(56, Math.floor((w * h) / 16000));
    particles = [];
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.18,
        vy: (Math.random() - 0.5) * 0.18,
        r: 1.2 + Math.random() * 1.6,
        hue: Math.random() < 0.5 ? '#ff6403' : (Math.random() < 0.5 ? '#4f85f6' : '#9b6ef3')
      });
    }
  }

  // ─── Mouse tracking
  canvas.addEventListener('mousemove', (e) => {
    const r = canvas.getBoundingClientRect();
    mouse.x = e.clientX - r.left;
    mouse.y = e.clientY - r.top;
    mouse.active = true;
  });
  canvas.addEventListener('mouseleave', () => { mouse.active = false; mouse.x = -9999; mouse.y = -9999; });

  // ─── Draw
  function draw() {
    t += 0.012;
    ctx.clearRect(0, 0, w, h);

    // ─ Map dot field (background)
    mapDots.forEach(d => {
      const px = d.x * w;
      const py = d.y * h;
      if (d.hot) {
        const pulse = 0.5 + 0.5 * Math.sin(t * d.speed + d.phase);
        // Outer glow ring
        const ringR = 6 + 10 * pulse;
        ctx.beginPath();
        ctx.arc(px, py, ringR, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(255, 100, 3, ${0.32 * (1 - pulse)})`;
        ctx.lineWidth = 1.2;
        ctx.stroke();

        ctx.beginPath();
        ctx.arc(px, py, 2.6, 0, Math.PI * 2);
        ctx.fillStyle = '#ff9a00';
        ctx.shadowColor = '#ff6403';
        ctx.shadowBlur = 10;
        ctx.fill();
        ctx.shadowBlur = 0;
      } else {
        ctx.beginPath();
        ctx.arc(px, py, d.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(120, 130, 210, 0.18)';
        ctx.fill();
      }
    });

    // ─ Particles — drift + mouse repulse
    particles.forEach(p => {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > w) p.vx *= -1;
      if (p.y < 0 || p.y > h) p.vy *= -1;

      if (mouse.active) {
        const dx = p.x - mouse.x;
        const dy = p.y - mouse.y;
        const d = Math.sqrt(dx*dx + dy*dy);
        if (d < 110) {
          const f = (110 - d) / 110 * 0.6;
          p.x += (dx / d) * f;
          p.y += (dy / d) * f;
        }
      }
    });

    // ─ Connections
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const a = particles[i], b = particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const d2 = dx*dx + dy*dy;
        if (d2 < 140 * 140) {
          const op = (1 - Math.sqrt(d2) / 140) * 0.18;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.strokeStyle = `rgba(255, 100, 3, ${op})`;
          ctx.lineWidth = 0.7;
          ctx.stroke();
        }
      }
    }

    // ─ Particle dots
    particles.forEach(p => {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = p.hue;
      ctx.shadowColor = p.hue;
      ctx.shadowBlur = 8;
      ctx.fill();
      ctx.shadowBlur = 0;
    });

    requestAnimationFrame(draw);
  }

  // ─── Init
  resize();
  window.addEventListener('resize', () => {
    clearTimeout(window.__hcResize);
    window.__hcResize = setTimeout(resize, 120);
  });
  draw();
})();
