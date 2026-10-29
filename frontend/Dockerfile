# Dev image: the source is bind-mounted by docker compose, node_modules lives in the image.
FROM node:22-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
CMD ["npm", "run", "dev"]
