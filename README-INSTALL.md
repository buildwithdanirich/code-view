# ColabVerse Questions app

The uploaded ZIP contained only Django's starter scaffold. This package replaces that scaffold with a public questions feed, discussion threads, likes, accepted answers, reputation, notifications, search, and tags.

## Install into your existing ColabVerse project

1. Back up your existing `questions/` directory and database.
2. Extract this archive at the project root, so `manage.py` and `questions/` are siblings.
3. Add `"questions"` to `INSTALLED_APPS` in `config/settings.py` (only once).
4. Add `path("questions/", include("questions.urls")),` to `urlpatterns` in `config/urls.py`; import `include` if necessary.
5. In your activated Django environment run:

   python3 manage.py makemigrations questions
   python3 manage.py migrate
   python3 manage.py check
   python3 manage.py test questions
   python3 manage.py runserver

6. Visit http://127.0.0.1:8000/questions/

The app intentionally has its own namespaced routes and CSS/JS to avoid modifying existing users and community apps. It uses your existing Django authentication system. You can add a Questions link to your site's global navigation later.

## Reputation

All users share one rating scale: 0-99 points = 1 star; 100-299 = 2; 300-699 = 3; 700-1499 = 4; 1500+ = 5. Likes on questions and comments grant +1; accepting an answer grants +20. Unlike/unaccept removes the awarded points. Users cannot like their own content or accept their own comments. Stars are calculated from points and will be available to display on the future profile page.

## Important limits / follow-up

- This package was assembled without a Django runtime in the build environment, so Django tests and migrations could not be executed here. You must run the commands above before treating it as production-ready.
- A generated migration is not included; `makemigrations` creates it using your installed Django version.
- Reputation from likes on content that is later deleted through cascade deletion is not recalculated automatically. Reconciliation logic and stronger abuse detection should be added before production deployment.
- Notifications are in-app, not real-time push notifications.
- Replies are one level deep; rich code editing, attachments, and developer profile integration are future work.
