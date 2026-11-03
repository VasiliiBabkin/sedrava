const key = "benchmark-counter-v0";
const output = document.querySelector<HTMLOutputElement>("#count");
if (!output) throw new Error("Missing count display");
const saved = window.localStorage.getItem(key);
let count: number = saved === null ? 0 : Number(saved);
if (!Number.isSafeInteger(count)) count = 0;
function render(): void {
  output!.textContent = String(count);
  window.localStorage.setItem(key, String(count));
}
document.querySelector<HTMLButtonElement>("#increment")!.addEventListener("click", () => {
  count += 1;
  render();
});
document.querySelector<HTMLButtonElement>("#decrement")!.addEventListener("click", () => {
  count -= 1;
  render();
});
document.querySelector<HTMLButtonElement>("#reset")!.addEventListener("click", () => {
  count = 0;
  render();
});
render();
