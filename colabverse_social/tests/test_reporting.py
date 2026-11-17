"""Security and functionality tests for ColabVerse content reporting."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from colabverse_admin.models import ContentReport
from community.models import (
    GroupInvitation,
    GroupMember,
    ProjectGroup,
)
from questions.models import Comment, Question


class ContentReportingTests(TestCase):
    """
    Verify that developers can report other developers'
    content without bypassing ownership or group permissions.
    """

    def setUp(self):
        """Create developers, content, and a private group."""

        User = get_user_model()

        # Developer A owns the question and private group.
        self.owner = User.objects.create_user(
            username="report_owner",
            password="TestPass123!",
        )

        # Developer B is an accepted group member.
        self.member = User.objects.create_user(
            username="report_member",
            password="TestPass123!",
        )

        # Developer C is not a group member.
        self.outsider = User.objects.create_user(
            username="report_outsider",
            password="TestPass123!",
        )

        # Developer D has a pending invitation.
        self.invited = User.objects.create_user(
            username="report_invited",
            password="TestPass123!",
        )

        # Create a question belonging to the owner.
        self.question = Question.objects.create(
            author=self.owner,
            title="How do Django permissions work?",
            body="I want to understand Django permissions.",
        )

        # Create a comment belonging to the owner.
        self.comment = Comment.objects.create(
            question=self.question,
            author=self.owner,
            body="Permissions control access to resources.",
        )

        # Create a reply belonging to the owner.
        self.reply = Comment.objects.create(
            question=self.question,
            author=self.owner,
            parent=self.comment,
            body="They should be checked on the server.",
        )

        # Create an invitation-only private group.
        self.group = ProjectGroup.objects.create(
            name="Backend Developers",
            description="Private backend development group.",
            owner=self.owner,
            is_private=True,
            join_policy="invite",
        )

        # Accepted membership is represented by GroupMember.
        GroupMember.objects.create(
            group=self.group,
            user=self.member,
            role="member",
        )

        # A pending invitation does not grant membership.
        GroupInvitation.objects.create(
            group=self.group,
            invited_by=self.owner,
            invited_user=self.invited,
            status="pending",
        )

    def report_url(self, kind, object_id):
        """Generate a contextual reporting URL."""

        return reverse(
            "colabverse_social:report_content",
            args=[kind, object_id],
        )

    # =====================================================
    # QUESTION REPORTING
    # =====================================================

    def test_developer_can_report_another_users_question(self):
        """A developer can report a question they do not own."""

        self.client.force_login(self.member)

        response = self.client.post(
            self.report_url("question", self.question.pk),
            {"reason": "This question contains abusive content."},
        )

        self.assertRedirects(
            response,
            reverse("colabverse_social:report_history"),
        )

        report = ContentReport.objects.get()

        self.assertEqual(report.reporter, self.member)
        self.assertEqual(report.kind, "question")
        self.assertEqual(report.object_id, self.question.pk)
        self.assertEqual(report.status, "open")

    def test_developer_cannot_report_own_question(self):
        """Question owners cannot report their own questions."""

        self.client.force_login(self.owner)

        url = self.report_url("question", self.question.pk)

        self.assertEqual(
            self.client.get(url).status_code,
            404,
        )

        self.assertEqual(
            self.client.post(
                url,
                {"reason": "Trying to report my own question."},
            ).status_code,
            404,
        )

        self.assertFalse(ContentReport.objects.exists())

    # =====================================================
    # COMMENT AND REPLY REPORTING
    # =====================================================

    def test_developer_can_report_another_users_comment(self):
        """A developer can report another developer's comment."""

        self.client.force_login(self.member)

        response = self.client.post(
            self.report_url("comment", self.comment.pk),
            {"reason": "This comment violates community rules."},
        )

        self.assertEqual(response.status_code, 302)

        report = ContentReport.objects.get()

        self.assertEqual(report.kind, "comment")
        self.assertEqual(report.object_id, self.comment.pk)

    def test_developer_can_report_another_users_reply(self):
        """Replies use the Comment model and reporting route."""

        self.client.force_login(self.member)

        response = self.client.post(
            self.report_url("comment", self.reply.pk),
            {"reason": "This reply contains harassment."},
        )

        self.assertEqual(response.status_code, 302)

        report = ContentReport.objects.get()

        self.assertEqual(report.kind, "comment")
        self.assertEqual(report.object_id, self.reply.pk)

    def test_developer_cannot_report_own_comment_or_reply(self):
        """Comment authors cannot report their own content."""

        self.client.force_login(self.owner)

        for comment in (self.comment, self.reply):

            with self.subTest(comment_id=comment.pk):

                response = self.client.post(
                    self.report_url("comment", comment.pk),
                    {"reason": "Trying to report my own content."},
                )

                self.assertEqual(response.status_code, 404)

        self.assertFalse(ContentReport.objects.exists())

    # =====================================================
    # PRIVATE GROUP REPORTING
    # =====================================================

    def test_accepted_member_can_report_private_group(self):
        """An accepted member can report a group they do not own."""

        self.client.force_login(self.member)

        url = self.report_url("group", self.group.pk)

        # The member can access the reporting form.
        self.assertEqual(
            self.client.get(url).status_code,
            200,
        )

        # The member can submit a report.
        response = self.client.post(
            url,
            {"reason": "This group is being used for harassment."},
        )

        self.assertEqual(response.status_code, 302)

        report = ContentReport.objects.get()

        self.assertEqual(report.reporter, self.member)
        self.assertEqual(report.kind, "group")
        self.assertEqual(report.object_id, self.group.pk)
        self.assertEqual(report.status, "open")

    def test_group_owner_cannot_report_own_group(self):
        """Group owners cannot report their own groups."""

        self.client.force_login(self.owner)

        url = self.report_url("group", self.group.pk)

        self.assertEqual(
            self.client.get(url).status_code,
            404,
        )

        self.assertEqual(
            self.client.post(
                url,
                {"reason": "Trying to report my own group."},
            ).status_code,
            404,
        )

        self.assertFalse(ContentReport.objects.exists())

    def test_non_member_cannot_report_private_group(self):
        """Developers outside a private group cannot report it."""

        self.client.force_login(self.outsider)

        url = self.report_url("group", self.group.pk)

        self.assertEqual(
            self.client.get(url).status_code,
            404,
        )

        self.assertEqual(
            self.client.post(
                url,
                {"reason": "Unauthorized reporting attempt."},
            ).status_code,
            404,
        )

        self.assertFalse(ContentReport.objects.exists())

    def test_pending_invitation_does_not_allow_reporting(self):
        """A pending invitation does not grant group access."""

        self.client.force_login(self.invited)

        response = self.client.post(
            self.report_url("group", self.group.pk),
            {"reason": "Trying to report before joining."},
        )

        self.assertEqual(response.status_code, 404)

        self.assertFalse(ContentReport.objects.exists())

    # =====================================================
    # DUPLICATE REPORT PROTECTION
    # =====================================================

    def test_duplicate_pending_report_is_not_created(self):
        """A developer cannot create two pending reports for one item."""

        self.client.force_login(self.member)

        url = self.report_url("question", self.question.pk)

        self.client.post(
            url,
            {"reason": "First report about this question."},
        )

        self.client.post(
            url,
            {"reason": "Second report about the same question."},
        )

        self.assertEqual(
            ContentReport.objects.filter(
                reporter=self.member,
                kind="question",
                object_id=self.question.pk,
            ).count(),
            1,
        )

    def test_different_developers_can_report_same_question(self):
        """Different developers can independently report one question."""

        url = self.report_url("question", self.question.pk)

        self.client.force_login(self.member)

        self.client.post(
            url,
            {"reason": "First developer's report."},
        )

        self.client.force_login(self.outsider)

        self.client.post(
            url,
            {"reason": "Second developer's report."},
        )

        self.assertEqual(ContentReport.objects.count(), 2)

    # =====================================================
    # REPORT HISTORY AND AUTHENTICATION
    # =====================================================

    def test_report_history_only_shows_own_reports(self):
        """Developers cannot see reports submitted by other users."""

        ContentReport.objects.create(
            reporter=self.member,
            kind="question",
            object_id=self.question.pk,
            reason="Member's report.",
        )

        ContentReport.objects.create(
            reporter=self.outsider,
            kind="question",
            object_id=self.question.pk,
            reason="Outsider's report.",
        )

        self.client.force_login(self.member)

        response = self.client.get(
            reverse("colabverse_social:report_history")
        )

        self.assertEqual(response.status_code, 200)

        reports = list(response.context["page"].object_list)

        self.assertEqual(len(reports), 1)
        self.assertEqual(reports[0].reporter, self.member)

    def test_anonymous_developer_must_log_in(self):
        """Unauthenticated visitors cannot submit reports."""

        self.client.logout()

        response = self.client.post(
            self.report_url("question", self.question.pk),
            {"reason": "Anonymous reporting attempt."},
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(ContentReport.objects.exists())

    def test_invalid_reporting_target_returns_404(self):
        """Unsupported content types cannot be reported."""

        self.client.force_login(self.member)

        response = self.client.post(
            self.report_url("invalid", self.question.pk),
            {"reason": "Invalid content type."},
        )

        self.assertEqual(response.status_code, 404)

        self.assertFalse(ContentReport.objects.exists())