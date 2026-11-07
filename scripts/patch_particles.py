#!/usr/bin/env python3
"""Apply reduced-motion + mobile density fixes to the hero particle text in events.html."""
import pathlib

p = pathlib.Path(__file__).resolve().parent.parent / 'templates' / 'events.html'
s = p.read_text(encoding='utf-8')

old1 = """        function renderHeroParticles() {
            if (!particleContainer || !window.initParticleText) return;
            if (typeof particleCleanup === 'function') {"""
new1 = """        const prefersReducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

        function renderHeroParticles() {
            if (!particleContainer || !window.initParticleText) return;
            // Respect reduced-motion and mobile/weak devices: show the static
            // fallback title instead of generating hundreds of DOM particles.
            if (prefersReducedMotion) {
                particleContainer.innerHTML = '';
                particleContainer.style.display = 'none';
                if (fallbackTitle) fallbackTitle.style.display = 'block';
                return;
            }
            if (typeof particleCleanup === 'function') {"""

old2 = "                density: 3,"
new2 = "                density: isMobileDevice ? 2 : 3,"

assert old1 in s, 'block 1 not found'
assert old2 in s, 'block 2 not found'

s = s.replace(old1, new1, 1)
s = s.replace(old2, new2, 1)

p.write_text(s, encoding='utf-8')
print('PATCH OK')
