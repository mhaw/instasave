
document.addEventListener('DOMContentLoaded', function() {
    const lightboxOverlay = document.getElementById('lightboxOverlay');
    if (lightboxOverlay) {
        const postItems = document.querySelectorAll('.post-item');
        const lightboxMedia = document.getElementById('lightboxMedia');
        const lightboxClose = document.getElementById('lightboxClose');

        // Show More/Show Less functionality
        document.querySelectorAll('.show-more-btn').forEach(button => {
            button.addEventListener('click', function(event) {
                event.stopPropagation(); // Prevent event from bubbling to post-item
                const fullCaption = this.nextElementSibling; // The full-caption paragraph
                const previewCaption = this.previousElementSibling; // The caption-preview paragraph

                if (fullCaption.style.display === 'none') {
                    fullCaption.style.display = 'block';
                    previewCaption.style.display = 'none';
                    this.textContent = 'Show Less';
                } else {
                    fullCaption.style.display = 'none';
                    previewCaption.style.display = 'block';
                    this.textContent = 'Show More';
                }
            });
        });

        postItems.forEach(item => {
            item.addEventListener('click', function(event) {
                // Prevent opening lightbox if a link or the show-more button inside the post-item is clicked
                if (event.target.tagName === 'A' || event.target.classList.contains('show-more-btn')) {
                    return;
                }

                const mediaPath = this.dataset.mediaPath;
                const mediaType = this.dataset.mediaType;

                lightboxMedia.innerHTML = ''; // Clear previous content

                if (mediaType === 'image') {
                    const img = document.createElement('img');
                    img.src = mediaPath;
                    lightboxMedia.appendChild(img);
                } else if (mediaType === 'video') {
                    const video = document.createElement('video');
                    video.src = mediaPath;
                    video.controls = true;
                    video.autoplay = true; // Autoplay video in lightbox
                    video.loop = true; // Loop video
                    lightboxMedia.appendChild(video);
                }

                lightboxOverlay.classList.add('visible');
            });
        });

        const closeLightbox = () => {
            lightboxOverlay.classList.remove('visible');
            const videoInLightbox = lightboxMedia.querySelector('video');
            if (videoInLightbox) {
                videoInLightbox.pause();
            }
        };

        lightboxClose.addEventListener('click', function(event) {
            event.preventDefault();
            closeLightbox();
        });

        lightboxOverlay.addEventListener('click', function(event) {
            if (event.target === lightboxOverlay) {
                closeLightbox();
            }
        });

        // Keyboard navigation for lightbox
        document.addEventListener('keydown', function(event) {
            if (event.key === 'Escape' && lightboxOverlay.classList.contains('visible')) {
                closeLightbox();
            }
        });
    }
});
