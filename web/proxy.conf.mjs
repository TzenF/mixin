// Proxy du serveur de dev : /api/* -> backend FastAPI (sans le préfixe /api).
// Dans Docker Compose, API_URL=http://api:8000 ; en local, http://localhost:8000.
export default {
  '/api': {
    target: process.env.API_URL ?? 'http://localhost:8000',
    changeOrigin: true,
    pathRewrite: { '^/api': '' },
  },
};
