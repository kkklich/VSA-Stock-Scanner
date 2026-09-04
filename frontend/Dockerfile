# StockPilot web — production image.
#
# Stage 1 builds the React app with Vite; stage 2 serves the resulting static
# files with Nginx and reverse-proxies /api to the backend container.

# ── Stage 1: build ────────────────────────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app

# npm ci needs both files and installs exactly what package-lock.json pins.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# VITE_API_URL stays EMPTY on purpose: the browser calls same-origin paths like
# /api/stocks/ranking, and the Nginx block below proxies them to the API
# container. Same origin means no CORS preflight and no hardcoded backend host.
ENV VITE_API_URL=""
RUN npm run build

# ── Stage 2: serve ────────────────────────────────────────────────────────────
FROM nginx:1.27-alpine

# Replace the default site with ours (SPA routing + /api proxy).
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

# Validate the Nginx config at BUILD time. A syntax error (or a misplaced
# rate-limit directive) then fails the CI/deploy build loudly instead of
# crash-looping the container in production. `nginx -t` checks config only —
# it does not bind ports or resolve the `api` upstream.
RUN nginx -t

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --quiet --spider http://127.0.0.1/healthz || exit 1
