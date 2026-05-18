#!/bin/sh

# migrate and load data
docker compose exec web python manage.py flush
echo Making migrations
docker compose exec web python manage.py makemigrations emedict
echo Migrating models
docker compose exec web python manage.py migrate
echo Loading data
docker compose exec web python manage.py loaddata emedictdata.json.gz --app emedict

docker compose exec web python manage.py createsuperuser
