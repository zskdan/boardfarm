FROM node:20-alpine AS build
RUN apk add --no-cache git
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
COPY .git/ .git/
RUN npm run build
RUN rm -rf .git

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
