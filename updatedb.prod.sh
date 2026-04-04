#!/bin/sh

# migrate and load data
docker compose -f docker-compose.prod.yml exec web python manage.py flush
echo Making migrations
docker compose -f docker-compose.prod.yml exec web python manage.py makemigrations emedict
echo Migrating models
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
echo "Loading data (might take a while)"
docker compose -f docker-compose.prod.yml exec web python manage.py loaddata emedictdata.json.gz --app emedict
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic
echo "(Re)building elasticsearch indices"
docker compose -f docker-compose.prod.yml exec web python manage.py search_index --rebuild

docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser
