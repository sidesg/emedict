#!/bin/sh

EXPATH=app/emedictdata.json

if [ -f "$EXPATH.gz" ]; then
    read -p "$EXPATH.gz apready exists. Overwrite? [y/N] " confirm
        case "$confirm" in
            [yY][eE][sS]|[yY])
                docker compose -f docker-compose.prod.yml exec web python manage.py dumpdata emedict > $EXPATH
                rm $EXPATH.gz
                gzip $EXPATH
                ;;
            *)
                exit 1
                ;;
        esac
else
    docker compose -f docker-compose.prod.yml exec web python manage.py dumpdata emedict > app/emedictdata.json
    gzip $EXPATH
fi
