/**
 * Liquid Fluid Ink Button Engine
 * Reusable high-craft micro-fluidic animation engine ported to Vanilla JS.
 * Features:
 *  - Dynamic cursor / touch origin tracking
 *  - Spring physics fluid blob expansion (spring = 150, damping = 24)
 *  - SVG feTurbulence organic breathing & feDisplacementMap fluid distortion
 *  - Multi-phase click impulse shockwave ripple with tension recoil and glide escape
 *  - SVG clipPath inverted text layer with zero DOM duplicate voiceover
 *  - Optimized for low-end mobile touch & desktop pointer 60+ FPS
 */

(function (window, document) {
  'use strict';

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const DEFAULT_NOISE_FREQUENCY = { baseX: 0.035, baseY: 0.08 };

  const clamp = (val, min, max) => Math.min(max, Math.max(min, val));

  function parseNoiseFrequency(value) {
    if (!value) return DEFAULT_NOISE_FREQUENCY;
    const tokens = String(value).trim().split(/\s+/).filter(Boolean);
    if (tokens.length === 0) return DEFAULT_NOISE_FREQUENCY;
    const x = Number(tokens[0]);
    const y = Number(tokens[1]);
    if (tokens.length === 1) {
      return !isNaN(x) && x >= 0 ? { baseX: x, baseY: x } : DEFAULT_NOISE_FREQUENCY;
    }
    return {
      baseX: !isNaN(x) && x >= 0 ? x : DEFAULT_NOISE_FREQUENCY.baseX,
      baseY: !isNaN(y) && y >= 0 ? y : DEFAULT_NOISE_FREQUENCY.baseY,
    };
  }

  function cloneInvertedContent(source, dest) {
    const fragment = document.createDocumentFragment();
    source.childNodes.forEach((node) => {
      const clone = node.cloneNode ? node.cloneNode(true) : (node.data ? document.createTextNode(node.data) : node);
      if (clone.nodeType === 1) {
        clone.removeAttribute('id');
        if (clone.querySelectorAll) {
          clone.querySelectorAll('[id]').forEach((el) => el.removeAttribute('id'));
        }
      }
      fragment.appendChild(clone);
    });

    if (fragment.normalize) fragment.normalize();
    if (fragment.querySelectorAll) {
      fragment.querySelectorAll('svg title, svg desc').forEach((el) => el.remove());
    }

    const walker = document.createTreeWalker(fragment, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    for (const text of textNodes) {
      const isInsideSvg = (typeof SVGElement !== 'undefined' && text.parentNode instanceof SVGElement) ||
        (text.parentNode && text.parentNode.namespaceURI === SVG_NS);
      if (!text.data.trim() || isInsideSvg) continue;
      const label = document.createElement('span');
      label.setAttribute('data-liquid-text', text.data);
      if (text.replaceWith) {
        text.replaceWith(label);
      } else if (text.parentNode) {
        text.parentNode.replaceChild(label, text);
      }
    }

    dest.replaceChildren(fragment);
  }

  let idCounter = 0;

  function initLiquidButton(btn, options) {
    if (!btn || btn.hasAttribute('data-no-liquid') || btn.hasAttribute('data-liquid-initialized')) return btn;
    if (btn.matches && btn.matches('#events .btn-card-rules, #events .btn-card-contact')) return btn;
    btn.setAttribute('data-liquid-initialized', 'true');
    btn.setAttribute('data-liquid-button', 'true');
    if (!btn.classList.contains('liquid-btn')) {
      btn.classList.add('liquid-btn');
    }

    const opts = options || {};
    const instanceId = 'liquid-ink-' + (++idCounter) + '-' + Math.random().toString(36).substring(2, 7);
    const filterId = instanceId + '-filter';
    const clipPathId = instanceId + '-clip';

    const noiseFreq = parseNoiseFrequency(btn.getAttribute('data-noise-frequency') || opts.noiseFrequency);

    // 1. Prepare DOM Layers
    // If children are not wrapped in data-liquid-content, wrap them
    let contentEl = btn.querySelector('[data-liquid-content]');
    if (!contentEl) {
      contentEl = document.createElement('span');
      contentEl.className = 'liquid-btn-content';
      contentEl.setAttribute('data-liquid-content', 'true');
      while (btn.firstChild) {
        contentEl.appendChild(btn.firstChild);
      }
      btn.appendChild(contentEl);
    }

    // Inverted overlay span
    let invertedEl = btn.querySelector('[data-liquid-inverted]');
    if (!invertedEl) {
      invertedEl = document.createElement('span');
      invertedEl.className = 'liquid-btn-inverted';
      invertedEl.setAttribute('data-liquid-inverted', 'true');
      invertedEl.setAttribute('aria-hidden', 'true');
      btn.appendChild(invertedEl);
    }

    btn.style.setProperty('--liquid-clip', `url(#${clipPathId})`);
    invertedEl.style.setProperty('--liquid-clip', `url(#${clipPathId})`);
    invertedEl.style.setProperty('clip-path', `url(#${clipPathId})`);
    invertedEl.style.setProperty('-webkit-clip-path', `url(#${clipPathId})`);
    invertedEl.style.opacity = '0';
    invertedEl.style.visibility = 'hidden';
    btn.style.removeProperty('-webkit-clip-path');
    btn.style.removeProperty('clip-path');

    // Synchronize inverted content
    const syncInverted = () => cloneInvertedContent(contentEl, invertedEl);
    syncInverted();

    const domObserver = new MutationObserver(syncInverted);
    domObserver.observe(contentEl, {
      subtree: true,
      childList: true,
      characterData: true,
      attributes: true,
    });

    // 2. Build SVG elements
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('class', 'liquid-btn-svg');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');

    const defs = document.createElementNS(SVG_NS, 'defs');

    const filter = document.createElementNS(SVG_NS, 'filter');
    filter.setAttribute('id', filterId);
    filter.setAttribute('x', '-35%');
    filter.setAttribute('y', '-45%');
    filter.setAttribute('width', '170%');
    filter.setAttribute('height', '190%');
    filter.setAttribute('color-interpolation-filters', 'sRGB');

    const feTurbulence = document.createElementNS(SVG_NS, 'feTurbulence');
    feTurbulence.setAttribute('type', 'fractalNoise');
    feTurbulence.setAttribute('baseFrequency', `${noiseFreq.baseX} ${noiseFreq.baseY}`);
    feTurbulence.setAttribute('numOctaves', '2');
    feTurbulence.setAttribute('seed', '8');
    feTurbulence.setAttribute('result', 'liquid-noise');

    const feDisplacementMap = document.createElementNS(SVG_NS, 'feDisplacementMap');
    feDisplacementMap.setAttribute('in', 'SourceGraphic');
    feDisplacementMap.setAttribute('in2', 'liquid-noise');
    feDisplacementMap.setAttribute('scale', '5');
    feDisplacementMap.setAttribute('xChannelSelector', 'R');
    feDisplacementMap.setAttribute('yChannelSelector', 'G');

    filter.appendChild(feTurbulence);
    filter.appendChild(feDisplacementMap);

    const clipPath = document.createElementNS(SVG_NS, 'clipPath');
    clipPath.setAttribute('id', clipPathId);
    clipPath.setAttribute('clipPathUnits', 'userSpaceOnUse');

    const clipEllipse = document.createElementNS(SVG_NS, 'ellipse');
    clipEllipse.setAttribute('cx', '0');
    clipEllipse.setAttribute('cy', '0');
    clipEllipse.setAttribute('rx', '0');
    clipEllipse.setAttribute('ry', '0');
    clipPath.appendChild(clipEllipse);

    defs.appendChild(filter);
    defs.appendChild(clipPath);
    svg.appendChild(defs);

    const blob = document.createElementNS(SVG_NS, 'ellipse');
    blob.setAttribute('filter', `url(#${filterId})`);
    blob.setAttribute('fill', 'var(--liquid-fill, #2563eb)');
    blob.setAttribute('cx', '0');
    blob.setAttribute('cy', '0');
    blob.setAttribute('rx', '0');
    blob.setAttribute('ry', '0');
    blob.style.display = 'none';
    svg.appendChild(blob);

    const ripple = document.createElementNS(SVG_NS, 'circle');
    ripple.setAttribute('filter', `url(#${filterId})`);
    ripple.setAttribute('fill', 'none');
    ripple.setAttribute('stroke', 'var(--liquid-active-text, #ffffff)');
    ripple.setAttribute('stroke-width', '2.4px');
    ripple.style.display = 'none';
    svg.appendChild(ripple);

    btn.insertBefore(svg, btn.firstChild);

    // 3. Fluid Physics & State Machine
    const state = {
      x: 0,
      y: 0,
      radius: 0,
      radiusVelocity: 0,
      pointerActive: false,
      focusActive: false,
      targetSpeed: 0,
      speed: 0,
      targetAngle: 0,
      angle: 0,
      stretch: 1,
      frame: 0,
      lastFrame: 0,
      lastPointerTime: 0,
      lastPointerX: 0,
      lastPointerY: 0,
      disabled: Boolean(btn.disabled),
      time: 0,
      unstableJitterX: 0,
      unstableJitterY: 0,
      randomSeed: 8,
      ringProgress: 0,
      ringPhase: 0,
      ringX: 0,
      ringY: 0,
      ringOriginX: 0,
      ringOriginY: 0,
      ringEscapeAngle: 0,
      ringPeakScale: 0.58,
      ringDipRatio: 0.86,
      ringSpeedMult: 1.0,
    };

    function getDimensions() {
      const rect = btn.getBoundingClientRect();
      return { width: btn.clientWidth, height: btn.clientHeight, rect };
    }

    function toLocalPoint(clientX, clientY) {
      const { rect, width, height } = getDimensions();
      if (!rect || width <= 0 || height <= 0 || rect.width <= 0 || rect.height <= 0) return null;
      return {
        x: clamp(((clientX - rect.left) * width) / rect.width, 0, width),
        y: clamp(((clientY - rect.top) * height) / rect.height, 0, height),
        width,
        height,
      };
    }

    function maxCornerDistance(w, h, x, y) {
      return Math.max(
        Math.hypot(x, y),
        Math.hypot(w - x, y),
        Math.hypot(x, h - y),
        Math.hypot(w - x, h - y)
      );
    }

    function setShapeAttributes(elem, rx, ry, angle) {
      if (!elem) return;
      const renderX = state.x + state.unstableJitterX;
      const renderY = state.y + state.unstableJitterY;
      elem.setAttribute('cx', String(renderX));
      elem.setAttribute('cy', String(renderY));
      elem.setAttribute('rx', String(Math.max(0, rx)));
      elem.setAttribute('ry', String(Math.max(0, ry)));
      elem.setAttribute('transform', `rotate(${angle} ${renderX} ${renderY})`);
    }

    function renderShape() {
      const { width, height } = getDimensions();
      if (width <= 0 || height <= 0) return;

      if (state.radius <= 0.05 && state.ringPhase === 0) {
        blob.style.display = 'none';
        invertedEl.style.opacity = '0';
        invertedEl.style.visibility = 'hidden';
      } else {
        blob.style.display = 'block';
        invertedEl.style.opacity = '1';
        invertedEl.style.visibility = 'visible';
      }

      const axisScale = Math.sqrt(state.stretch);
      const rx = state.radius * axisScale;
      const ry = state.radius / axisScale;

      setShapeAttributes(blob, rx, ry, state.angle);
      setShapeAttributes(clipEllipse, rx, ry, state.angle);

      const prefersReducedMotion =
        typeof window !== 'undefined' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      if (!prefersReducedMotion) {
        const breathingFactor = 1 + Math.sin(state.time * 2.5) * 0.12;
        feTurbulence.setAttribute(
          'baseFrequency',
          `${(noiseFreq.baseX * breathingFactor).toFixed(4)} ${(noiseFreq.baseY * (2 - breathingFactor)).toFixed(4)}`
        );
      }

      const livingFluidShimmer = Math.sin(state.time * 4) * 1.5;
      const ringTurbulence = state.ringPhase > 0 ? (1 - state.ringProgress) * 18 : 0;
      const displacementScale = prefersReducedMotion
        ? 0
        : 4.5 + state.speed * 18 + livingFluidShimmer + ringTurbulence;
      feDisplacementMap.setAttribute('scale', displacementScale.toFixed(2));

      // Shockwave Ripple
      if (state.ringPhase > 0) {
        const baseDimension = Math.min(width, height);
        const peakRadius = baseDimension * state.ringPeakScale;
        const recoilDipRadius = peakRadius * state.ringDipRatio;
        let currentRadius = 0;
        let currentOpacity = 0;
        let currentStroke = 2.4;

        if (state.ringPhase === 1) {
          const easeOut = 1 - Math.pow(1 - state.ringProgress, 3);
          currentRadius = easeOut * peakRadius;
          currentOpacity = 0.95 - state.ringProgress * 0.12;
          currentStroke = 2.6 - state.ringProgress * 0.3;
        } else if (state.ringPhase === 2) {
          const recoilFactor = Math.sin(state.ringProgress * Math.PI);
          currentRadius = peakRadius - recoilFactor * (peakRadius - recoilDipRadius);
          currentOpacity = 0.88;
          currentStroke = 2.3;
        } else if (state.ringPhase === 3) {
          const p = state.ringProgress;
          currentRadius = recoilDipRadius + p * Math.max(width, height) * 0.85;
          currentOpacity = Math.max(0, 0.88 * (1 - p));
          currentStroke = Math.max(1, 2.3 * (1 - p * 0.6));
        }

        ripple.setAttribute('cx', String(state.ringX + state.unstableJitterX * 0.5));
        ripple.setAttribute('cy', String(state.ringY + state.unstableJitterY * 0.5));
        ripple.setAttribute('r', String(Math.max(0, currentRadius)));
        ripple.setAttribute('opacity', String(Math.max(0, currentOpacity)));
        ripple.style.strokeWidth = `${currentStroke.toFixed(2)}px`;
        ripple.style.display = 'block';
      } else {
        ripple.style.display = 'none';
      }
    }

    function scheduleFrame() {
      if (state.frame === 0) {
        state.frame = window.requestAnimationFrame(tick);
      }
    }

    function tick(now) {
      state.frame = 0;

      const dt = state.lastFrame === 0 ? 1 / 60 : clamp((now - state.lastFrame) / 1000, 1 / 240, 1 / 30);
      state.lastFrame = now;
      state.time += dt;

      const { width, height } = getDimensions();
      if (width <= 0 || height <= 0) return;

      const prefersReducedMotion =
        typeof window !== 'undefined' &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      if (prefersReducedMotion) {
        state.unstableJitterX = 0;
        state.unstableJitterY = 0;
        state.ringPhase = 0;
        state.ringProgress = 0;
      } else {
        const t = state.time;
        state.unstableJitterX =
          Math.sin(t * 3.7) * 2.2 +
          Math.sin(t * 7.1 + 1.2) * 1.4 +
          Math.cos(t * 11.3) * 0.8;
        state.unstableJitterY =
          Math.cos(t * 3.1) * 1.8 +
          Math.sin(t * 6.3 + 2.4) * 1.2 +
          Math.sin(t * 13.1) * 0.6;
      }

      const speedLerp = 1 - Math.exp(-dt / 0.105);
      state.speed += (state.targetSpeed - state.speed) * speedLerp;
      state.targetSpeed = 0;

      const breathingStretch = prefersReducedMotion ? 0 : Math.sin(state.time * 2.8) * 0.04;
      const desiredStretch = 1 + state.speed * 0.55 + (state.pointerActive ? breathingStretch : 0);
      state.stretch += (desiredStretch - state.stretch) * (1 - Math.exp(-dt / 0.08));

      const angleDelta = ((state.targetAngle - state.angle + 540) % 360) - 180;
      state.angle += angleDelta * (1 - Math.exp(-dt / 0.075));

      if (!prefersReducedMotion) {
        if (state.ringPhase === 1) {
          state.ringProgress += dt * 3.8 * state.ringSpeedMult;
          if (state.ringProgress >= 1) {
            state.ringPhase = 2;
            state.ringProgress = 0;
          }
        } else if (state.ringPhase === 2) {
          state.ringProgress += dt * 7.8 * state.ringSpeedMult;
          if (state.ringProgress >= 1) {
            state.ringPhase = 3;
            state.ringProgress = 0;
          }
        } else if (state.ringPhase === 3) {
          state.ringProgress += dt * 3.5 * state.ringSpeedMult;
          const glideSpeed = Math.max(width, height) * 1.55 * dt * state.ringSpeedMult;
          state.ringX += Math.cos(state.ringEscapeAngle) * glideSpeed;
          state.ringY += Math.sin(state.ringEscapeAngle) * glideSpeed;

          if (state.ringProgress >= 1) {
            state.ringPhase = 0;
            state.ringProgress = 0;
          }
        }
      }

      const active = (state.pointerActive || state.focusActive) && !state.disabled;
      const targetRadius = active
        ? maxCornerDistance(width, height, state.x, state.y) * Math.sqrt(state.stretch) * 1.14
        : 0;

      if (prefersReducedMotion) {
        state.radius = targetRadius;
        state.radiusVelocity = 0;
      } else {
        const spring = 150;
        const damping = 24;
        const acceleration = (targetRadius - state.radius) * spring - state.radiusVelocity * damping;
        state.radiusVelocity += acceleration * dt;
        state.radius += state.radiusVelocity * dt;
      }

      if (state.radius < 0) {
        state.radius = 0;
        state.radiusVelocity = 0;
      }

      renderShape();

      if (active || state.ringPhase > 0 || Math.abs(state.radius) > 0.1) {
        state.frame = window.requestAnimationFrame(tick);
      } else {
        state.lastFrame = 0;
        state.radius = 0;
        state.radiusVelocity = 0;
        state.stretch = 1;
        state.speed = 0;
        state.ringPhase = 0;
        renderShape();
      }
    }

    function setOrigin(clientX, clientY) {
      const point = toLocalPoint(clientX, clientY);
      if (!point) return;
      state.x = point.x;
      state.y = point.y;
      renderShape();
    }

    function triggerClickImpulse(clientX, clientY) {
      const point = toLocalPoint(clientX, clientY);
      if (!point) return;
      const { x: posX, y: posY, width, height } = point;

      state.ringOriginX = posX;
      state.ringOriginY = posY;
      state.ringX = posX;
      state.ringY = posY;
      state.ringPhase = 1;
      state.ringProgress = 0;

      state.randomSeed = Math.floor(Math.random() * 9999) + 1;
      feTurbulence.setAttribute('seed', String(state.randomSeed));

      state.ringPeakScale = 0.56 + Math.random() * 0.09;
      state.ringDipRatio = 0.82 + Math.random() * 0.08;
      state.ringSpeedMult = 0.92 + Math.random() * 0.22;

      const centerX = width / 2;
      const centerY = height / 2;
      const dx = posX - centerX;
      const dy = posY - centerY;
      const baseAngle = Math.hypot(dx, dy) > 2 ? Math.atan2(dy, dx) : -Math.PI / 2;
      const anglePerturbation = (Math.random() - 0.5) * 0.85;
      state.ringEscapeAngle = baseAngle + anglePerturbation;

      const randomImpulse = 130 + Math.random() * 50;
      state.radiusVelocity += randomImpulse;

      if (typeof navigator !== 'undefined' && 'vibrate' in navigator) {
        try {
          navigator.vibrate(10);
        } catch (e) {
          // ignore
        }
      }

      scheduleFrame();
    }

    function updatePointerVelocity(e) {
      const now = performance.now();
      if (state.lastPointerTime > 0) {
        const elapsed = Math.max(8, now - state.lastPointerTime);
        const dx = e.clientX - state.lastPointerX;
        const dy = e.clientY - state.lastPointerY;
        const pixelsPerMs = Math.hypot(dx, dy) / elapsed;
        state.targetSpeed = clamp(pixelsPerMs / 1.65, 0, 1);
        if (Math.hypot(dx, dy) > 0.5) {
          state.targetAngle = Math.atan2(dy, dx) * (180 / Math.PI);
        }
      }
      state.lastPointerTime = now;
      state.lastPointerX = e.clientX;
      state.lastPointerY = e.clientY;
    }

    function syncSize() {
      const { width, height } = getDimensions();
      if (width <= 0 || height <= 0) return;
      if (state.x === 0 && state.y === 0) {
        state.x = width / 2;
        state.y = height / 2;
      }
      renderShape();
    }

    // 4. Attach Event Listeners
    btn.addEventListener('pointerenter', (e) => {
      if (state.disabled || e.pointerType === 'touch') return;
      state.pointerActive = true;
      setOrigin(e.clientX, e.clientY);
      updatePointerVelocity(e);
      scheduleFrame();
    });

    btn.addEventListener('pointermove', (e) => {
      if (state.disabled || e.pointerType === 'touch') return;
      setOrigin(e.clientX, e.clientY);
      updatePointerVelocity(e);
      scheduleFrame();
    });

    btn.addEventListener('pointerleave', (e) => {
      if (e.pointerType !== 'touch') {
        setOrigin(e.clientX, e.clientY);
      }
      state.pointerActive = false;
      state.lastPointerTime = 0;
      btn.classList.remove('is-pressed');
      scheduleFrame();
    });

    btn.addEventListener('pointerdown', (e) => {
      if (state.disabled) return;
      state.pointerActive = true;
      btn.classList.add('is-pressed');
      setOrigin(e.clientX, e.clientY);
      triggerClickImpulse(e.clientX, e.clientY);
    });

    btn.addEventListener('pointerup', (e) => {
      btn.classList.remove('is-pressed');
      if (e.pointerType === 'touch') {
        state.pointerActive = false;
        scheduleFrame();
      }
    });

    btn.addEventListener('pointercancel', () => {
      state.pointerActive = false;
      state.lastPointerTime = 0;
      btn.classList.remove('is-pressed');
      scheduleFrame();
    });

    btn.addEventListener('focus', () => {
      const focusVisible = btn.matches(':focus-visible') && !state.disabled;
      state.focusActive = !!focusVisible;
      if (focusVisible) {
        const { width, height } = getDimensions();
        state.x = width / 2;
        state.y = height / 2;
        renderShape();
        scheduleFrame();
      }
    });

    btn.addEventListener('blur', () => {
      state.focusActive = false;
      scheduleFrame();
    });

    window.addEventListener('blur', () => {
      state.pointerActive = false;
      state.focusActive = false;
      state.lastPointerTime = 0;
      btn.classList.remove('is-pressed');
      scheduleFrame();
    });

    if (typeof ResizeObserver !== 'undefined') {
      const ro = new ResizeObserver(() => {
        syncSize();
        scheduleFrame();
      });
      ro.observe(btn);
    } else {
      window.addEventListener('resize', () => {
        syncSize();
        scheduleFrame();
      });
    }

    // Initial size and paint
    syncSize();

    return btn;
  }

  // Selectors for automatic button enhancement
  const BUTTON_SELECTORS = [
    '.liquid-btn',
    '[data-liquid-button]',
    '.header-cta-classic',
    '#headerRegisterBtn',
    '.hero-explore-btn',
    '.hero-rules-btn',
    '.hero-contact-btn',
    '#discCascadeRegister',
    '#discCascadeRules',
    '#discCascadeCall',
    '#discCascadeIndexButton',
    '.btn-card-register',
    '.btn-card-rules',
    '.btn-card-contact',
    '.clean-black-submit-btn',
    '#submitBtn',
    '#upiPayButton',
    '#copyUpiBtn',
    '.track-btn-primary',
    '.track-btn-secondary'
  ].join(',');

  function initAllLiquidButtons(rootNode) {
    const scope = rootNode || document;
    if (!scope.querySelectorAll) return;
    const targets = scope.querySelectorAll(BUTTON_SELECTORS);
    targets.forEach((elem) => {
      // Keep legacy effects everywhere except the Events-grid Rules/Contact controls.
      if (elem.matches && elem.matches('#events .btn-card-rules, #events .btn-card-contact')) return;

      // Exclude small icon toggles or explicitly opted-out elements
      if ((elem.closest && elem.closest('.celestial-theme-toggle')) || elem.hasAttribute('data-no-liquid')) {
        return;
      }
      try {
        initLiquidButton(elem);
      } catch (err) {
        console.warn('Liquid button init fallback for element:', elem, err);
      }
    });
  }

  // Auto initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initAllLiquidButtons(document));
  } else {
    initAllLiquidButtons(document);
  }

  // Observe dynamically rendered elements (e.g. event cards filtered/swapped, modals)
  if (typeof MutationObserver !== 'undefined') {
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.type === 'childList' && m.addedNodes.length > 0) {
          m.addedNodes.forEach((node) => {
            if (node.nodeType === Node.ELEMENT_NODE) {
              if (node.matches && node.matches(BUTTON_SELECTORS)) {
                initLiquidButton(node);
              }
              initAllLiquidButtons(node);
            }
          });
        }
      }
    });

    if (document.body) {
      observer.observe(document.body, { childList: true, subtree: true });
    } else {
      document.addEventListener('DOMContentLoaded', () => {
        observer.observe(document.body, { childList: true, subtree: true });
      });
    }
  }

  // Expose global methods
  window.initLiquidButton = initLiquidButton;
  window.initAllLiquidButtons = initAllLiquidButtons;

})(window, document);
