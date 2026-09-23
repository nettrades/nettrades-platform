# THIS IS A VERY OLD FILE GPUSTACK HAS BEEN REPLACED BY NVIDIA DYNAMO SO THIS COULD BE REMOVED 
# AND REPLACED WITH THE NVIDIA DYNAMO FILE

Update the DaemonSet manifest to include a liveness probe that hits /health:
yaml
# apps/gpustack/wg-peer-manager.yaml
          livenessProbe:
            httpGet:
              path: /health
              port: 8081
            initialDelaySeconds: 10
            periodSeconds: 30