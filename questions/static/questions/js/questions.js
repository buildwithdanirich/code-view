document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.reply-toggle').forEach(button => {
    button.addEventListener('click', () => {
      const form = document.getElementById(button.dataset.target);
      if (form) form.hidden = !form.hidden;
    });
  });
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
});

