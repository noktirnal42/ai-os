const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (!reduceMotion) {
  const visual = document.querySelector('.hero-visual');
  window.addEventListener('pointermove', (event) => {
    if (!visual) return;
    const x = (event.clientX / window.innerWidth - 0.5) * 8;
    const y = (event.clientY / window.innerHeight - 0.5) * 8;
    visual.style.transform = `translate(${x}px, ${y}px)`;
  }, {passive: true});
}
