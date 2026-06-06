# =============================================================================
# Section: H – Container image for the WireGuard peer manager.
# Build: docker build -t wg-peer-manager:latest .
# =============================================================================
FROM golang:1.21-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY main.go .
RUN CGO_ENABLED=0 go build -o /wg-peer-manager .

FROM alpine:3.19
RUN apk add --no-cache wireguard-tools   # wg-quick, wg
COPY --from=builder /wg-peer-manager /usr/local/bin/wg-peer-manager
CMD ["/usr/local/bin/wg-peer-manager"]