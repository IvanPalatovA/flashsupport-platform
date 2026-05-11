FROM node:20.12.2-bookworm-slim

ENV NODE_ENV=production

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --include=dev

COPY tsconfig.json tsconfig.server.json ./
COPY src ./src
COPY config ./config

RUN npm run build

EXPOSE 8060

CMD ["node", "dist/main.js"]
