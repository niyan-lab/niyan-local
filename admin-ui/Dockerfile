FROM node:20-alpine AS build
WORKDIR /app
# Empty: the browser calls /api on the console origin. nginx proxies that to niyan-api.
# Set a URL only when this image is served somewhere that cannot proxy /api.
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL
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
