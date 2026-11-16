document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('id_avatar');
    const preview = document.getElementById('cv-avatar-preview');
    const fallback = document.getElementById('cv-avatar-fallback');
    if (!input || !preview) return;
    input.addEventListener('change', () => {
        const file = input.files && input.files[0];
        if (!file || !file.type.startsWith('image/')) return;
        const reader = new FileReader();
        reader.onload = () => {
            preview.src = reader.result;
            preview.hidden = false;
            if (fallback) fallback.hidden = true;
        };
        reader.readAsDataURL(file);
    });
});
