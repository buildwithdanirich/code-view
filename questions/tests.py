from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from .models import Question, Comment, QuestionLike, CommentLike, Reputation, Notification

class QuestionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.alex = User.objects.create_user(username='alex_cv', password='strong-test-password-123')
        cls.sam = User.objects.create_user(username='sam_cv', password='strong-test-password-123')
        cls.question = Question.objects.create(author=cls.alex, title='How do I run Django?', body='Need help with manage.py')

    def test_public_feed_and_detail(self):
        self.assertContains(self.client.get(reverse('questions:feed')), self.question.title)
        self.assertContains(self.client.get(reverse('questions:detail', args=[self.question.pk])), self.question.title)

    def test_login_required_to_post(self):
        self.assertEqual(self.client.get(reverse('questions:create')).status_code, 302)

    def test_create_question(self):
        self.client.force_login(self.sam)
        response = self.client.post(reverse('questions:create'), {'title':'Why is my import failing?', 'body':'I have an import error.', 'tags_text':'python,django'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Question.objects.filter(author=self.sam).count(), 1)

    def test_like_toggle_reputation_and_no_self_like(self):
        self.client.force_login(self.sam)
        url = reverse('questions:like', args=[self.question.pk])
        self.client.post(url)
        self.assertEqual(QuestionLike.objects.count(), 1)
        self.assertEqual(Reputation.objects.get(user=self.alex).points, 1)
        self.client.post(url)
        self.assertEqual(QuestionLike.objects.count(), 0)
        self.assertEqual(Reputation.objects.get(user=self.alex).points, 0)
        self.client.force_login(self.alex)
        self.client.post(url)
        self.assertEqual(QuestionLike.objects.count(), 0)

    def test_comment_like_and_accepted_answer(self):
        self.client.force_login(self.sam)
        self.client.post(reverse('questions:comment', args=[self.question.pk]), {'body':'Try python manage.py runserver'})
        comment = Comment.objects.get(author=self.sam)
        self.client.force_login(self.alex)
        self.client.post(reverse('questions:comment_like', args=[comment.pk]))
        self.assertEqual(Reputation.objects.get(user=self.sam).points, 1)
        self.client.post(reverse('questions:accept', args=[comment.pk]))
        self.assertTrue(Comment.objects.get(pk=comment.pk).is_accepted)
        self.assertEqual(Reputation.objects.get(user=self.sam).points, 21)
        self.client.post(reverse('questions:accept', args=[comment.pk]))
        self.assertEqual(Reputation.objects.get(user=self.sam).points, 1)

    def test_only_question_author_accepts(self):
        comment = Comment.objects.create(question=self.question, author=self.sam, body='Here is the answer')
        self.client.force_login(self.sam)
        self.assertEqual(self.client.post(reverse('questions:accept', args=[comment.pk])).status_code, 404)

    def test_cannot_edit_others_question(self):
        self.client.force_login(self.sam)
        self.assertEqual(self.client.get(reverse('questions:edit', args=[self.question.pk])).status_code, 404)

    def test_get_does_not_like(self):
        self.client.force_login(self.sam)
        self.assertEqual(self.client.get(reverse('questions:like', args=[self.question.pk])).status_code, 405)
        self.assertEqual(QuestionLike.objects.count(), 0)

    def test_notifications_are_private(self):
        Notification.objects.create(recipient=self.alex, actor=self.sam, question=self.question, message='liked your question')
        self.client.force_login(self.sam)
        self.assertNotContains(self.client.get(reverse('questions:notifications')), 'liked your question')

    def test_star_thresholds(self):
        rep = Reputation(user=self.sam, points=0)
        self.assertEqual(rep.stars, 1)
        for points, stars in [(100,2),(300,3),(700,4),(1500,5),(10000,5)]:
            rep.points = points
            self.assertEqual(rep.stars, stars)
