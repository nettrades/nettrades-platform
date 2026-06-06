bash

bash .env.generator.sh > .env
chmod 600 .env

This eliminates the manual secret-generation step entirely. The install-nettrades.sh script already does this internally; this standalone version is for users who want to generate secrets without running the full wizard.


init-db.sql is ran by deploy/docker/deploy-single.sh  so double check it to make sure it could run it.