FROM node:20-alpine AS build
WORKDIR /app
# No API URL is baked in: public/config.js (apiBaseUrl "") makes the browser
# call /api on the console origin, and nginx.conf proxies that to niyan-api.
# Helm replaces config.js via a ConfigMap. Only the gateway URL is build-time.
ARG VITE_GATEWAY_URL=http://localhost:4000
ENV VITE_GATEWAY_URL=$VITE_GATEWAY_URL
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
LABEL org.opencontainers.image.licenses="Apache-2.0"
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
