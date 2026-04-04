# Sumerian dictionary with faceted tagging

Emedict is a dictionary of the Sumerian language; its main features are
1. The ability to tag each entry with an arbitrary number of categorized tags
1. The separation of each "word" into a lemma with an arbitrary number of optionally categorized forms.
    * For most parts of speech, only one uncategorized form is necessary. A noun like *ninda* will only have a single form.
    * For verbs, forms minimally represent ḫamtû and marû forms. Forms can have mutliple types to capture the distribution of more complex suppletive verbs such as ŋen/du/sub/ere or dug/e/di.

The application can be run in dev mode with `docker compose up -d` or in prod mode with `docker compose -f docker-compose.prod.yml up -d`. Both will be available on `localhost:8000`.

Before using either environment, run `updatedb.sh` or `updatedb.prod.sh` to load the database data, create a pgadmin super user, and (for production), collect the static files to be served.

Currently this web app is designed to be run locally, as it depends on the user being able to access the admin pages of each entry. The prod environment is closer to production-ready, but is not secure.

Initial lexicographical data come from the Electronic Pennsylvania Sumerian Dictionary (ePSD2; http://oracc.museum.upenn.edu/epsd2/).
