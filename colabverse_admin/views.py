from django.apps import apps
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .models import AdminAuditLog, ContentReport, SupportTicket
from .services import get_counts, health_report


def is_admin(user):
    return user.is_authenticated and user.is_active and user.is_staff


admin_required = user_passes_test(is_admin, login_url='/login/')


def model_for(label):
    try:
        return apps.get_model(label)
    except LookupError:
        return None


def page_for(request, queryset):
    return Paginator(queryset, 20).get_page(request.GET.get('page'))


def log_action(request, action, target):
    AdminAuditLog.objects.create(actor=request.user, action=action, target=str(target)[:180])


@never_cache
@admin_required
def dashboard(request):
    counts = get_counts(get_user_model())
    counts['comments'] = get_optional_count('questions.Comment')
    counts['reports'] = ContentReport.objects.filter(status='open').count()
    counts['support'] = SupportTicket.objects.exclude(status='resolved').count()
    return render(request, 'colabverse_admin/dashboard.html', {
        'counts': counts,
        'recent_audit': AdminAuditLog.objects.select_related('actor')[:8],
    })


def get_optional_count(label):
    model = model_for(label)
    return model.objects.count() if model else None


@never_cache
@admin_required
def users(request):
    model = get_user_model()
    qs = model._default_manager.all().order_by('-pk')
    term = request.GET.get('q', '').strip()[:100]
    if term:
        search = Q()
        for field in (model.USERNAME_FIELD, 'email', 'first_name', 'last_name'):
            if any(f.name == field for f in model._meta.fields):
                search |= Q(**{f'{field}__icontains': term})
        qs = qs.filter(search)
    return render(request, 'colabverse_admin/users.html', {'page': page_for(request, qs), 'term': term})


@require_POST
@admin_required
def toggle_user_active(request, user_id):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only superusers can change account status.')
    target = get_object_or_404(get_user_model(), pk=user_id)
    if target.pk == request.user.pk or target.is_superuser:
        messages.error(request, 'You cannot change your own account or another superuser.')
    else:
        target.is_active = not target.is_active
        target.save(update_fields=['is_active'])
        log_action(request, 'user.toggle_active', target.pk)
        messages.success(request, 'Account status updated.')
    return redirect('colabverse_admin:users')


@never_cache
@admin_required
def groups(request):
    model = model_for('community.ProjectGroup')
    if model is None:
        return render(request, 'colabverse_admin/records.html', {'heading': 'Communities & groups', 'unavailable': True})
    qs = model.objects.all().order_by('-pk')
    term = request.GET.get('q', '').strip()[:100]
    if term:
        qs = qs.filter(name__icontains=term)
    page = page_for(request, qs)
    return render(request, 'colabverse_admin/groups.html', {'page': page, 'term': term})


@never_cache
@admin_required
def questions(request):
    model = model_for('questions.Question')
    if model is None:
        return render(request, 'colabverse_admin/records.html', {'heading': 'Questions', 'unavailable': True})
    qs = model.objects.select_related('author').order_by('-pk')
    term = request.GET.get('q', '').strip()[:100]
    if term:
        qs = qs.filter(Q(title__icontains=term) | Q(body__icontains=term))
    return render(request, 'colabverse_admin/questions.html', {'page': page_for(request, qs), 'term': term})


@never_cache
@admin_required
def answers(request):
    # ColabVerse uses questions.Comment as the answer model.
    model = model_for('questions.Comment')
    if model is None:
        return render(request, 'colabverse_admin/records.html', {'heading': 'Answers', 'unavailable': True})
    qs = model.objects.select_related('author', 'question').order_by('-pk')
    return render(request, 'colabverse_admin/answers.html', {'page': page_for(request, qs)})


@require_POST
@admin_required
def delete_content(request, kind, object_id):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only superusers can delete content.')
    label = {'question': 'questions.Question', 'comment': 'questions.Comment'}.get(kind)
    if not label or model_for(label) is None:
        return HttpResponseForbidden('Unsupported content type.')
    obj = get_object_or_404(model_for(label), pk=object_id)
    # Explicit typed confirmation avoids accidental removal.
    if request.POST.get('confirm') != 'DELETE':
        messages.error(request, 'Type DELETE to confirm permanent deletion.')
    else:
        obj.delete()
        log_action(request, 'content.delete', f'{kind}:{object_id}')
        messages.success(request, 'Content deleted.')
    return redirect('colabverse_admin:questions' if kind == 'question' else 'colabverse_admin:answers')


@never_cache
@admin_required
def meetings(request):
    model = model_for('community.GroupMeeting')
    if model is None:
        return render(request, 'colabverse_admin/records.html', {'heading': 'Meetings', 'unavailable': True})
    qs = model.objects.select_related('group').order_by('-pk')
    status = request.GET.get('status', '')
    if status in ('active', 'ended'):
        qs = qs.filter(status=status)
    return render(request, 'colabverse_admin/meetings.html', {'page': page_for(request, qs), 'status': status})


@never_cache
@admin_required
def reports(request):
    qs = ContentReport.objects.select_related('reporter').order_by('-created_at')
    return render(request, 'colabverse_admin/reports.html', {'page': page_for(request, qs)})


@require_POST
@admin_required
def report_status(request, report_id):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only superusers can resolve reports.')
    report = get_object_or_404(ContentReport, pk=report_id)
    status = request.POST.get('status')
    if status not in dict(ContentReport.STATUS_CHOICES):
        return HttpResponseForbidden('Invalid status')
    report.status = status
    report.reviewed_at = timezone.now()
    report.save(update_fields=['status', 'reviewed_at'])
    log_action(request, 'report.status', f'{report.pk}:{status}')
    return redirect('colabverse_admin:reports')


@never_cache
@admin_required
def support(request):
    qs = SupportTicket.objects.select_related('requester').order_by('-created_at')
    return render(request, 'colabverse_admin/support.html', {'page': page_for(request, qs)})


@require_POST
@admin_required
def support_update(request, ticket_id):
    if not request.user.is_superuser:
        return HttpResponseForbidden('Only superusers can update tickets.')
    ticket = get_object_or_404(SupportTicket, pk=ticket_id)
    status = request.POST.get('status')
    if status not in dict(SupportTicket.STATUS_CHOICES):
        return HttpResponseForbidden('Invalid status')
    ticket.status = status
    ticket.admin_reply = request.POST.get('admin_reply', '')[:10000]
    ticket.save(update_fields=['status', 'admin_reply', 'updated_at'])
    log_action(request, 'support.update', ticket.pk)
    messages.success(request, 'Ticket updated.')
    return redirect('colabverse_admin:support')


@never_cache
@admin_required
def security(request):
    return render(request, 'colabverse_admin/security.html', {
        'page': page_for(request, AdminAuditLog.objects.select_related('actor').all()),
    })


@never_cache
@admin_required
def health(request):
    return render(request, 'colabverse_admin/health.html', {'report': health_report()})


@never_cache
@admin_required
def health_status(request):
    return JsonResponse(health_report(), headers={'Cache-Control': 'no-store'})
