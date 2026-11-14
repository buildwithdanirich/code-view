from django.urls import path
from . import views

app_name = "questions"
urlpatterns = [
    path("", views.question_list, name="list"),
    path("ask/", views.question_create, name="create"),
    path("<int:pk>/", views.question_detail, name="detail"),
    path("<int:pk>/edit/", views.question_edit, name="edit"),
    path("<int:pk>/delete/", views.question_delete, name="delete"),
    path("<int:pk>/answer/", views.answer_create, name="answer_create"),
    path("<int:pk>/vote/", views.vote_question, name="vote_question"),
    path("answers/<int:pk>/edit/", views.answer_edit, name="answer_edit"),
    path("answers/<int:pk>/delete/", views.answer_delete, name="answer_delete"),
    path("answers/<int:pk>/accept/", views.accept_answer, name="accept_answer"),
    path("answers/<int:pk>/vote/", views.vote_answer, name="vote_answer"),
]
