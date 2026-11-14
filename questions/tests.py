from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import Answer, Question, QuestionVote

class QuestionsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(username="qa_owner", password="TestPass123!")
        self.other = User.objects.create_user(username="qa_other", password="TestPass123!")
        self.question = Question.objects.create(author=self.owner, title="How can I fix this Django error?", body="I get an error when running migrations in my project.")

    def test_public_list_and_detail(self):
        self.assertEqual(self.client.get(reverse("questions:list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("questions:detail", args=[self.question.pk])).status_code, 200)

    def test_ask_requires_login(self):
        self.assertEqual(self.client.get(reverse("questions:create")).status_code, 302)

    def test_create_question(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("questions:create"), {"title": "Why does my Django view return 404?", "body": "I am trying to load a URL and Django returns a 404 error.", "tag_names": "django, python"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Question.objects.count(), 2)

    def test_cannot_edit_others_question(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("questions:edit", args=[self.question.pk])).status_code, 403)

    def test_owner_cannot_vote_own_question(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse("questions:vote_question", args=[self.question.pk]), {"value": 1}).status_code, 403)

    def test_vote_toggle(self):
        self.client.force_login(self.other)
        url = reverse("questions:vote_question", args=[self.question.pk])
        self.client.post(url, {"value": 1})
        self.assertEqual(QuestionVote.objects.count(), 1)
        self.client.post(url, {"value": 1})
        self.assertEqual(QuestionVote.objects.count(), 0)

    def test_only_author_accepts_answer(self):
        answer = Answer.objects.create(question=self.question, author=self.other, body="Try checking the URL configuration.")
        url = reverse("questions:accept_answer", args=[answer.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.question.refresh_from_db()
        self.assertEqual(self.question.accepted_answer_id, answer.pk)
