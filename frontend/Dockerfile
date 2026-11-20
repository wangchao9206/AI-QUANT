FROM node:22.14.0-alpine3.21 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts \
    && npm install --no-save \
        @rollup/rollup-linux-x64-musl@4.64.5 \
        @esbuild/linux-x64@0.25.12
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27.4-alpine
USER root
RUN mkdir -p /var/lib/nginx/asset-archive/assets \
    && chown -R 101:101 /var/lib/nginx/asset-archive
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --chmod=755 archive-assets.sh /docker-entrypoint.d/40-archive-assets.sh
USER 101:101
EXPOSE 8080
