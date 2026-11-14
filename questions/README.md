# ColabVerse Questions app

Django Q&A module with questions, answers, accepted solutions, tags, votes, search, filters, responsive templates, and tests.

## Installation
1. Back up your existing questions folder.
2. Replace the questions folder with this one.
3. Add `"questions",` to `INSTALLED_APPS` in `config/settings.py`.
4. Add `path("questions/", include("questions.urls")),` to `config/urls.py` urlpatterns, and import `include` from `django.urls`.
5. Run `python3 manage.py makemigrations questions` then `python3 manage.py migrate`.
6. Run `python3 manage.py test questions`.
7. Visit `/questions/`.

The app uses your project's existing authentication (`login` URL name). HTML contains no inline CSS or JavaScript.

## Security notes
- Posting and modifying content require login; edit/delete restricted to authors.
- Only question owners may accept answers; users cannot vote on their own content.
- POST + CSRF required for state changes; code snippets displayed escaped, not executed.
- Voting and tag creation need further concurrency/hardening work for very high traffic; deployment requires standard Django production security settings.
- Generated migrations are intentionally not bundled because they must be created against your installed Django version and existing database.
