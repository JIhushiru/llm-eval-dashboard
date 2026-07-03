FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
# Shared API token (empty = auth gate disabled). Baked in at build time because
# NEXT_PUBLIC_* vars are inlined into the client bundle.
ARG NEXT_PUBLIC_API_TOKEN=
ENV NEXT_PUBLIC_API_TOKEN=$NEXT_PUBLIC_API_TOKEN

RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
