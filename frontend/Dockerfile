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
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
USER 101:101
EXPOSE 8080
