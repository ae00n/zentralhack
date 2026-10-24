// Programmatic focus without a visible ring (FRONTPAGE_POLISH 6: no ring on page load). The element gets
// focus (so the keys and the automation-bias rule keep working), and the ring shows again from the first
// key press, through the normal :focus-visible styles.
const ATTR = "data-quiet-focus";

export function quietFocus(el: HTMLElement | null | undefined) {
  if (!el) return;
  el.setAttribute(ATTR, "");
  el.focus({ preventScroll: true });
  const clear = () => {
    el.removeAttribute(ATTR);
    window.removeEventListener("keydown", clear, true);
    el.removeEventListener("blur", clear);
  };
  window.addEventListener("keydown", clear, true);
  el.addEventListener("blur", clear);
}
