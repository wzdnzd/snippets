if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/static/service-worker.js')
            .then(registration => {
                console.log('ServiceWorker注册成功:', registration.scope);
            })
            .catch(error => {
                console.log('ServiceWorker注册失败:', error);
            });
    });
}

document.addEventListener('DOMContentLoaded', () => {
    const copyrightYear = document.querySelector('.copyright script');
    if (copyrightYear) {
        copyrightYear.textContent = new Date().getFullYear();
    }
});
