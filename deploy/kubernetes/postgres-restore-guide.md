# PostgreSQL CNPG Restore Procedure

## Prerequisites
- Access to the Kubernetes cluster with `kubectl` and `cnpg` plugin installed.
- The latest backup file (stored on the configured backup destination, e.g., S3 bucket or NFS)
- The CNPG operator must be running

## Steps

1. Identify the backup to restore:
   ```bash
   kubectl cnpg backups list odoo-db -n backend
   
or run

   kubectl get backups -n backend

Find the backup you want (e.g., odoo-db-daily-20260513020000).

    Create a restore cluster
    Create a file restore-cluster.yaml:
    yaml

    apiVersion: postgresql.cnpg.io/v1
    kind: Cluster
    metadata:
      name: odoo-db-restored
      namespace: backend
    spec:
      instances: 3       # same as original
      storage:
        size: 100Gi      # same or larger
      bootstrap:
        recovery:
          backup:
            name: odoo-db-daily-20260513020000
          recoveryTarget:
            targetTime: "2026-05-13T02:00:00Z"   # optional, point in time
      externalClusters:
        - name: original-cluster
          barmanObjectStore:
            destinationPath: s3://your-bucket/   # same as original backup config
            s3Credentials:
              accessKeyId:
                name: s3-creds
                key: ACCESS_KEY_ID
              secretAccessKey:
                name: s3-creds
                key: ACCESS_SECRET

    Apply it:
    bash

    kubectl apply -f restore-cluster.yaml

    Wait for the restore to complete
    bash

    kubectl wait --for=condition=ready cluster/odoo-db-restored -n backend --timeout=600s

    The cluster will initialise from the backup and then start accepting connections.

    Verify the data
    Connect to the restored primary and verify that Odoo tables exist:
    bash

    kubectl exec -n backend odoo-db-restored-1 -- psql -U odoo -c "\dt"

    Switch Odoo to use the restored database

        Update the Odoo Deployment environment variable HOST to point to the restored cluster’s read-write service: odoo-db-restored-rw.backend.svc.cluster.local.

        Optionally, scale down the old PostgreSQL cluster to avoid confusion.

    Clean up the original cluster (if no longer needed)
    bash

    kubectl delete cluster odoo-db -n backend

3.3 Important Notes

    The barmanObjectStore section must exactly match the backup configuration of the original cluster.

    If you use volume snapshots instead of object store backups, the procedure differs; refer to CNPG documentation.

    Always test restore in a non-production environment first.