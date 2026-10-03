# Image de développement : serveur Angular avec rechargement à chaud.
# Le code source est monté en volume par docker-compose.yml.
FROM node:24-slim
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
EXPOSE 4200
CMD ["npx", "ng", "serve", "--host", "0.0.0.0", "--poll", "1000"]
