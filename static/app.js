document.querySelectorAll(".flash-ok").forEach((el) => setTimeout(() => el.remove(), 6000));
document.querySelectorAll("form[data-confirm]").forEach((f) =>
  f.addEventListener("submit", (e) => { if (!confirm(f.dataset.confirm)) e.preventDefault(); })
);
