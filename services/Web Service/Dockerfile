# syntax=docker/dockerfile:1.7
FROM node:20.12.2-bookworm-slim AS deps

ENV NODE_ENV=production
ENV NPM_CONFIG_FUND=false
ENV NPM_CONFIG_AUDIT=false

WORKDIR /app

COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --include=dev

FROM deps AS builder

COPY tsconfig.json tsconfig.server.json ./
COPY src ./src
COPY config ./config

RUN npm run build
RUN npm prune --omit=dev

FROM node:20.12.2-bookworm-slim AS runtime

ENV NODE_ENV=production
ENV NPM_CONFIG_FUND=false
ENV NPM_CONFIG_AUDIT=false

WORKDIR /app

COPY package.json package-lock.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY config ./config

EXPOSE 8060

CMD ["node", "dist/main.js"]
