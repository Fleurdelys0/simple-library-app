/* Theme management and theme-aware particles */
(function () {
  const THEME_KEY = 'theme';
  const PARTICLE_COLORS = {
    dark: ['#bbdefb', '#90caf9', '#64b5f6'],
    light: ['#0d47a1', '#1976d2', '#64b5f6']
  };

  let fallback = {
    rafId: null,
    onResize: null,
    particles: [],
    ctx: null,
    canvas: null,
  };

  function prefersReducedMotion() {
    try { return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch (e) { return false; }
  }

  function updateToggleUI(theme) {
    const el = document.getElementById('themeToggle');
    if (!el) return;
    const isLight = theme === 'light';
    try { el.checked = isLight; } catch (e) {}
    el.setAttribute('aria-checked', isLight ? 'true' : 'false');
  }

  function setTheme(theme, save = true) {
    document.documentElement.setAttribute('data-theme', theme);
    if (save) {
      try { localStorage.setItem(THEME_KEY, theme); } catch (e) {}
    }
    updateToggleUI(theme);
    reinitParticles(theme);
  }

  function getSavedTheme() {
    try { return localStorage.getItem(THEME_KEY); } catch (e) { return null; }
  }

  // tsParticles or particles.js if available, else canvas fallback
  function initParticles(theme) {
    const colors = PARTICLE_COLORS[theme] || PARTICLE_COLORS.dark;
    const count = 80;

    // tsParticles
    if (window.tsParticles && typeof window.tsParticles.load === 'function') {
      window.tsParticles.load('particles', {
        fpsLimit: 60,
        background: { color: { value: 'transparent' } },
        particles: {
          number: { value: count, density: { enable: true, area: 800 } },
          color: { value: colors },
          links: { enable: !prefersReducedMotion(), color: colors[1], opacity: 0.25, distance: 130, width: 1 },
          move: { enable: true, speed: prefersReducedMotion() ? 0.2 : 0.6, outModes: { default: 'out' } },
          opacity: { value: { min: 0.2, max: 0.6 } },
          size: { value: { min: 1, max: 3 } }
        },
        detectRetina: true
      });
      return;
    }

    // particles.js
    if (window.particlesJS) {
      window.particlesJS('particles', {
        particles: {
          number: { value: count, density: { enable: true, value_area: 800 } },
          color: { value: colors },
          line_linked: { enable: !prefersReducedMotion(), distance: 130, color: colors[1], opacity: 0.25, width: 1 },
          move: { enable: true, speed: prefersReducedMotion() ? 0.2 : 0.6, out_mode: 'out' },
          opacity: { value: 0.5 },
          size: { value: 2, random: true }
        },
        retina_detect: true
      });
      return;
    }

    // Canvas fallback (simple particles)
    const canvas = document.getElementById('particles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    fallback.canvas = canvas;
    fallback.ctx = ctx;

    function resize() {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    }
    resize();

    const speed = prefersReducedMotion() ? 0.15 : 0.6;

    class Particle {
      constructor() {
        this.reset();
      }
      reset() {
        this.x = Math.random() * canvas.width;
        this.y = Math.random() * canvas.height;
        this.size = Math.random() * 2.5 + 1;
        this.speedX = (Math.random() * speed) - (speed / 2);
        this.speedY = (Math.random() * speed) - (speed / 2);
        this.color = colors[Math.floor(Math.random() * colors.length)] + (theme === 'dark' ? '' : '');
      }
      update() {
        this.x += this.speedX;
        this.y += this.speedY;
        if (this.x > canvas.width || this.x < 0) this.speedX *= -1;
        if (this.y > canvas.height || this.y < 0) this.speedY *= -1;
      }
      draw() {
        ctx.fillStyle = this.color + (theme === 'dark' ? 'cc' : '66');
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    fallback.particles = [];
    for (let i = 0; i < count; i++) fallback.particles.push(new Particle());

    function animate() {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (let i = 0; i < fallback.particles.length; i++) {
        const p = fallback.particles[i];
        p.update();
        p.draw();
      }
      fallback.rafId = requestAnimationFrame(animate);
    }
    animate();

    fallback.onResize = () => {
      resize();
      // Recreate particles to fill new space evenly
      fallback.particles = [];
      for (let i = 0; i < count; i++) fallback.particles.push(new Particle());
    };
    window.addEventListener('resize', fallback.onResize);
  }

  function reinitParticles(theme) {
    // tsParticles cleanup
    if (window.tsParticles) {
      try {
        const dom = typeof window.tsParticles.domItem === 'function' ? window.tsParticles.domItem(0) : (window.tsParticles.dom && window.tsParticles.dom()[0]);
        if (dom && typeof dom.destroy === 'function') dom.destroy();
      } catch (e) {}
    }
    // particles.js cleanup
    if (window.pJSDom && window.pJSDom.length) {
      try {
        window.pJSDom[0].pJS.fn.vendors.destroypJS();
        window.pJSDom = [];
      } catch (e) {}
    }
    // fallback cleanup
    if (fallback.rafId) {
      cancelAnimationFrame(fallback.rafId);
      fallback.rafId = null;
    }
    if (fallback.onResize) {
      window.removeEventListener('resize', fallback.onResize);
      fallback.onResize = null;
    }
    if (fallback.ctx) {
      try { fallback.ctx.clearRect(0, 0, fallback.canvas.width, fallback.canvas.height); } catch (e) {}
    }
    initParticles(theme);
  }

  function init() {
    // initial theme from localStorage or existing html attribute
    const saved = getSavedTheme();
    const initial = (saved === 'light' || saved === 'dark') ? saved : (document.documentElement.getAttribute('data-theme') || 'dark');
    setTheme(initial, false);

    const el = document.getElementById('themeToggle');
    if (el) {
      el.addEventListener('change', () => {
        const next = el.checked ? 'light' : 'dark';
        setTheme(next, true);
      });
    }

    // init particles once DOM is ready
    initParticles(initial);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
