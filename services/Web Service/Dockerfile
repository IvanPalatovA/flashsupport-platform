FROM node:20.12.2-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts && npm install -g typescript
COPY tsconfig.json tsconfig.server.json ./
COPY src ./src
COPY config ./config
RUN npm run build

FROM nginx:1.25-alpine
COPY --from=build /app/dist/public /usr/share/nginx/html
COPY config/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]