Update the DaemonSet manifest to include a liveness probe that hits /health:
yaml
# apps/gpustack/wg-peer-manager.yaml
          livenessProbe:
            httpGet:
              path: /health
              port: 8081
            initialDelaySeconds: 10
            periodSeconds: 30