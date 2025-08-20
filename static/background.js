'use strict';

// Reduced motion respect
(function () {
  try {
    var sysReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var pref = localStorage.getItem('motion') || 'on'; // 'on' | 'off' | 'auto'
    var REDUCED = (pref === 'off') ? true : (pref === 'on' ? false : sysReduced);
    if (REDUCED) return; // arka plan animasyonu başlatma
  } catch (e) {
    // devam et
  }

  const circleCount = 150;
  const circlePropCount = 8;
  const circlePropsLength = circleCount * circlePropCount;
  const baseSpeed = 0.1;
  const rangeSpeed = 1;
  const baseTTL = 150;
  const rangeTTL = 200;
  const baseRadius = 100;
  const rangeRadius = 200;
  const rangeHue = 60;
  const xOff = 0.0015;
  const yOff = 0.0015;
  const zOff = 0.0015;
  const HUE_INCREMENT = 0.15; // Renk döngüsünü yavaşlat
  // Tema duyarlı renkler
  const LIGHT_BG = 'hsla(0,0%,98%,1)';
  const DARK_BG = 'hsla(0,0%,5%,1)';

  let IS_LIGHT = (() => {
    try {
      const attr = document.documentElement.getAttribute('data-theme');
      if (attr) return attr === 'light';
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches;
    } catch (_) { return false; }
  })();

  let BG_COLOR = IS_LIGHT ? LIGHT_BG : DARK_BG;
  let FILL_SAT = IS_LIGHT ? 55 : 60; // doygunluk
  let FILL_LUM = IS_LIGHT ? 60 : 30; // aydınlık

  // Tema değişimini izle
  try {
    const mo = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === 'attributes' && m.attributeName === 'data-theme') {
          const curr = document.documentElement.getAttribute('data-theme');
          IS_LIGHT = curr ? (curr === 'light') : (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches);
          BG_COLOR = IS_LIGHT ? LIGHT_BG : DARK_BG;
          FILL_SAT = IS_LIGHT ? 55 : 60;
          FILL_LUM = IS_LIGHT ? 60 : 30;
        }
      }
    });
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  } catch (e) {}

  const TAU = Math.PI * 2;

  let container;
  let canvas;
  let ctx;
  let circleProps;
  let simplex;
  let baseHue;
  let rafId = null;

  function rand(n = 1) { return Math.random() * n; }
  function fadeInOut(life, ttl) {
    const t = life / ttl;
    return Math.sin(t * Math.PI); // 0->1->0 smooth
  }

  function setup() {
    if (typeof SimplexNoise === 'undefined') {
      console.warn('SimplexNoise bulunamadı, arka plan etkisi devre dışı.');
      return;
    }
    createCanvas();
    resize();
    initCircles();
    draw();
  }

  function initCircles() {
    circleProps = new Float32Array(circlePropsLength);
    simplex = new SimplexNoise();
    baseHue = 220;

    for (let i = 0; i < circlePropsLength; i += circlePropCount) {
      initCircle(i);
    }
  }

  function initCircle(i) {
    let x, y, n, t, speed, vx, vy, life, ttl, radius, hue;

    x = rand(canvas.a.width);
    y = rand(canvas.a.height);
    n = simplex.noise3D(x * xOff, y * yOff, baseHue * zOff);
    t = rand(TAU);
    speed = baseSpeed + rand(rangeSpeed);
    vx = speed * Math.cos(t);
    vy = speed * Math.sin(t);
    life = 0;
    ttl = baseTTL + rand(rangeTTL);
    radius = baseRadius + rand(rangeRadius);
    hue = baseHue + n * rangeHue;

    circleProps.set([x, y, vx, vy, life, ttl, radius, hue], i);
  }

  function updateCircles() {
    baseHue += HUE_INCREMENT;
    for (let i = 0; i < circlePropsLength; i += circlePropCount) {
      updateCircle(i);
    }
  }

  function updateCircle(i) {
    let i2 = 1 + i, i3 = 2 + i, i4 = 3 + i, i5 = 4 + i, i6 = 5 + i, i7 = 6 + i, i8 = 7 + i;
    let x, y, vx, vy, life, ttl, radius, hue;

    x = circleProps[i];
    y = circleProps[i2];
    vx = circleProps[i3];
    vy = circleProps[i4];
    life = circleProps[i5];
    ttl = circleProps[i6];
    radius = circleProps[i7];
    hue = circleProps[i8];

    drawCircle(x, y, life, ttl, radius, hue);

    life++;

    circleProps[i] = x + vx;
    circleProps[i2] = y + vy;
    circleProps[i5] = life;

    (checkBounds(x, y, radius) || life > ttl) && initCircle(i);
  }

  function drawCircle(x, y, life, ttl, radius, hue) {
    ctx.a.save();
    ctx.a.fillStyle = `hsla(${hue},${FILL_SAT}%,${FILL_LUM}%,${fadeInOut(life, ttl)})`;
    ctx.a.beginPath();
    ctx.a.arc(x, y, radius, 0, TAU);
    ctx.a.fill();
    ctx.a.closePath();
    ctx.a.restore();
  }

  function checkBounds(x, y, radius) {
    return (
      x < -radius ||
      x > canvas.a.width + radius ||
      y < -radius ||
      y > canvas.a.height + radius
    );
  }

  function createCanvas() {
    container = document.querySelector('.content--canvas') || document.body;
    canvas = {
      a: document.createElement('canvas'),
      b: document.createElement('canvas')
    };
    canvas.b.style.position = 'fixed';
    canvas.b.style.top = '0';
    canvas.b.style.left = '0';
    canvas.b.style.width = '100%';
    canvas.b.style.height = '100%';
    canvas.b.style.zIndex = '-1';
    canvas.b.style.pointerEvents = 'none';
    container.appendChild(canvas.b);
    ctx = {
      a: canvas.a.getContext('2d'),
      b: canvas.b.getContext('2d')
    };
  }

  function resize() {
    const { innerWidth, innerHeight } = window;

    canvas.a.width = innerWidth;
    canvas.a.height = innerHeight;

    ctx.a.drawImage(canvas.b, 0, 0);

    canvas.b.width = innerWidth;
    canvas.b.height = innerHeight;

    ctx.b.drawImage(canvas.a, 0, 0);
  }

  function render() {
    ctx.b.save();
    ctx.b.filter = 'blur(50px)';
    ctx.b.drawImage(canvas.a, 0, 0);
    ctx.b.restore();
  }

  function draw() {
    ctx.a.clearRect(0, 0, canvas.a.width, canvas.a.height);
    ctx.b.fillStyle = BG_COLOR;
    ctx.b.fillRect(0, 0, canvas.b.width, canvas.b.height);
    updateCircles();
    render();
    rafId = window.requestAnimationFrame(draw);
  }

  function cleanup() {
    try { rafId && cancelAnimationFrame(rafId); } catch (_) {}
    try { if (canvas && canvas.b && canvas.b.parentNode) canvas.b.parentNode.removeChild(canvas.b); } catch (_) {}
  }

  window.addEventListener('load', setup);
  window.addEventListener('resize', resize);
  window.addEventListener('beforeunload', cleanup);
})();
