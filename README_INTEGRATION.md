# ColabVerse: Help & Support, Reports, Followers

This ZIP contains one **additive Django app** (`colabverse_social`). It reuses existing `colabverse_admin.models.SupportTicket` and `ContentReport` tables. It creates one new `Follow` table.

## Install (from the Django project root)

1. Copy the `colabverse_social/` folder alongside `users/`, `community/`, and `colabverse_admin/`. Do **not** replace any existing application.
2. In `config/settings.py`, append `"colabverse_social.apps.ColabverseSocialConfig"` to `INSTALLED_APPS`. Ensure `colabverse_admin` is installed too.
3. In `config/urls.py`, import `include` if needed, then add this URL entry **before any catch-all route**:

   ```python
   path("social/", include("colabverse_social.urls")),
   ```

4. Run:

   ```bash
   python3 manage.py check
   python3 manage.py makemigrations --check --dry-run colabverse_social
   python3 manage.py migrate
   python3 manage.py test colabverse_social
   python3 manage.py runserver
   ```

5. Open these pages while logged in:
   - `/social/support/` — submit and view support tickets and admin replies.
   - `/social/reports/` — submit and track your reports.
   - `/social/developers/` — search users and follow/unfollow them.

6. To link from existing templates:

   ```django
   <a href="{% url 'colabverse_social:support_home' %}">Help &amp; Support</a>
   <a href="{% url 'colabverse_social:report_create' %}">Report</a>
   <a href="{% url 'colabverse_social:developer_list' %}">Developers</a>
   ```

   For a specific question, comment, or group, use:

   ```django
   <a href="{% url 'colabverse_social:report_create' %}?kind=question&amp;object_id={{ question.pk }}">Report question</a>
   ```

   On existing developer profile templates, link to `{% url 'colabverse_social:follow_profile' profile_user.get_username %}` using your actual profile user variable. The app also provides its own standalone follow profile page.

## Behavior and limitations

- All pages require login. Only the owner sees their support tickets and reports. Admins continue to use the existing `/admin/reports/` and `/admin/support/` screens.
- Reporting supports the existing kinds `question`, `comment`, and `group`; the target must exist. It does not yet report users directly because the existing `ContentReport.KIND_CHOICES` does not include `user`.
- Report reason is free text, not predefined categories. Duplicate **pending** reports from the same reporter and target are checked in the application, not transactionally guaranteed; add a conditional DB constraint if strict concurrency protection is needed.
- Follows are public and one-way, like TikTok: following does not require approval. The database prevents duplicate follows and self-follows. No notifications, private-account approvals, follower feed, or user blocking are included.
- Report target IDs can be entered manually on the standalone form; linking from actual content is preferable. Access checks for private groups/content must be added based on your existing membership permissions before exposing report links for restricted content.
- Existing `/developers/<username>/` profile pages are untouched. The new profile view is at `/social/developers/<username>/`.
- Existing `ContentReport` and `SupportTicket` models and admin views are not changed. No migrations are needed for those models.
- `tests/test_features.py` assumes a username-based user model; adapt its test fixture if your custom user model uses email as USERNAME_FIELD.
- This package is a project integration starter, **not a verified deployment against your exact repository**. Review authentication, template navigation, permissions, anti-spam throttling, and your deployment configuration before production use.
