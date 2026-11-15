from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from .forms import QuestionForm, CommentForm
from .models import Tag, Question, Comment, QuestionLike, CommentLike, Notification, Reputation
from .services import adjust_reputation, notify


def feed(request):
    qs = Question.objects.select_related('author').prefetch_related('tags').annotate(like_count=Count('likes', distinct=True), comment_count=Count('comments', distinct=True))
    term = request.GET.get('q', '').strip()[:100]
    tag = request.GET.get('tag', '').strip()[:50]
    sort = request.GET.get('sort', 'new')
    if term: qs = qs.filter(Q(title__icontains=term) | Q(body__icontains=term) | Q(tags__name__icontains=term)).distinct()
    if tag: qs = qs.filter(tags__slug=tag)
    qs = qs.order_by('-like_count', '-created_at') if sort == 'popular' else qs.order_by('-created_at')
    page = Paginator(qs, 15).get_page(request.GET.get('page'))
    return render(request, 'questions/feed.html', {'page_obj': page, 'term': term, 'active_tag': tag, 'sort': sort, 'popular_tags': Tag.objects.annotate(total=Count('questions')).order_by('-total')[:12]})


def detail(request, pk):
    question = get_object_or_404(Question.objects.select_related('author').prefetch_related('tags'), pk=pk)
    comments = list(Comment.objects.filter(question=question).select_related('author').annotate(like_count=Count('likes')).order_by('created_at'))
    roots = [c for c in comments if c.parent_id is None]
    by_parent = {}
    for comment in comments:
        if comment.parent_id: by_parent.setdefault(comment.parent_id, []).append(comment)
    for comment in comments: comment.thread_replies = by_parent.get(comment.pk, [])
    liked_questions = QuestionLike.objects.filter(user=request.user, question=question).exists() if request.user.is_authenticated else False
    liked_comments = set(CommentLike.objects.filter(user=request.user, comment__question=question).values_list('comment_id', flat=True)) if request.user.is_authenticated else set()
    return render(request, 'questions/detail.html', {'question': question, 'roots': roots, 'comment_form': CommentForm(), 'liked_question': liked_questions, 'liked_comments': liked_comments, 'like_count': question.likes.count()})

@login_required
def create(request):
    form = QuestionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            question = form.save(commit=False)
            question.author = request.user
            question.save()
            for name in form.cleaned_data['tags_text']:
                slug = slugify(name)[:50]
                if slug:
                    tag, _ = Tag.objects.get_or_create(slug=slug, defaults={'name': name})
                    question.tags.add(tag)
        messages.success(request, 'Your question is live!')
        return redirect('questions:detail', pk=question.pk)
    return render(request, 'questions/form.html', {'form': form, 'heading': 'Ask the community'})

@login_required
def edit(request, pk):
    question = get_object_or_404(Question, pk=pk, author=request.user)
    form = QuestionForm(request.POST or None, instance=question, initial={'tags_text': ', '.join(question.tags.values_list('name', flat=True))})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            form.save()
            question.tags.clear()
            for name in form.cleaned_data['tags_text']:
                slug = slugify(name)[:50]
                if slug:
                    tag, _ = Tag.objects.get_or_create(slug=slug, defaults={'name': name})
                    question.tags.add(tag)
        return redirect('questions:detail', pk=pk)
    return render(request, 'questions/form.html', {'form': form, 'heading': 'Edit question'})

@login_required
@require_POST
def delete(request, pk):
    question = get_object_or_404(Question, pk=pk, author=request.user)
    question.delete()
    messages.success(request, 'Question deleted.')
    return redirect('questions:feed')

@login_required
@require_POST
def toggle_question_like(request, pk):
    question = get_object_or_404(Question.objects.select_related('author'), pk=pk)
    if question.author_id == request.user.pk:
        messages.error(request, 'You cannot like your own question.')
    else:
        with transaction.atomic():
            like, created = QuestionLike.objects.get_or_create(question=question, user=request.user)
            if created:
                adjust_reputation(question.author, 1)
                notify(question.author, request.user, question, 'liked your question')
            else:
                like.delete()
                adjust_reputation(question.author, -1)
    return redirect('questions:detail', pk=pk)

@login_required
@require_POST
def comment(request, pk):
    question = get_object_or_404(Question, pk=pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        parent_id = request.POST.get('parent_id')
        parent = get_object_or_404(Comment, pk=parent_id, question=question) if parent_id else None
        if parent and parent.parent_id:
            messages.error(request, 'Replies can only be one level deep.')
        else:
            entry = form.save(commit=False)
            entry.author = request.user
            entry.question = question
            entry.parent = parent
            entry.save()
            notify(parent.author if parent else question.author, request.user, question, 'replied to your comment' if parent else 'commented on your question')
            messages.success(request, 'Comment posted.')
    else:
        messages.error(request, 'Please enter a valid comment.')
    return redirect('questions:detail', pk=pk)

@login_required
@require_POST
def toggle_comment_like(request, pk):
    entry = get_object_or_404(Comment.objects.select_related('author', 'question'), pk=pk)
    if entry.author_id == request.user.pk:
        messages.error(request, 'You cannot like your own comment.')
    else:
        with transaction.atomic():
            like, created = CommentLike.objects.get_or_create(comment=entry, user=request.user)
            if created:
                adjust_reputation(entry.author, 1)
                notify(entry.author, request.user, entry.question, 'liked your comment')
            else:
                like.delete()
                adjust_reputation(entry.author, -1)
    return redirect('questions:detail', pk=entry.question_id)

@login_required
@require_POST
def accept(request, pk):
    entry = get_object_or_404(Comment.objects.select_related('question', 'author'), pk=pk)
    if entry.question.author_id != request.user.pk:
        raise Http404
    if entry.author_id == request.user.pk:
        messages.error(request, 'You cannot accept your own comment.')
        return redirect('questions:detail', pk=entry.question_id)
    with transaction.atomic():
        existing = Comment.objects.select_for_update().filter(question=entry.question, is_accepted=True).first()
        if existing and existing.pk == entry.pk:
            existing.is_accepted = False
            existing.save(update_fields=['is_accepted'])
            adjust_reputation(existing.author, -20)
        else:
            if existing:
                existing.is_accepted = False
                existing.save(update_fields=['is_accepted'])
                adjust_reputation(existing.author, -20)
            entry.is_accepted = True
            entry.save(update_fields=['is_accepted'])
            adjust_reputation(entry.author, 20)
            notify(entry.author, request.user, entry.question, 'accepted your answer')
    return redirect('questions:detail', pk=entry.question_id)

@login_required
@require_POST
def delete_comment(request, pk):
    entry = get_object_or_404(Comment, pk=pk, author=request.user)
    question_id = entry.question_id
    if entry.is_accepted: adjust_reputation(entry.author, -20)
    entry.delete()
    return redirect('questions:detail', pk=question_id)

@login_required
def notifications(request):
    qs = Notification.objects.filter(recipient=request.user).select_related('actor', 'question')[:50]
    return render(request, 'questions/notifications.html', {'notifications': qs})

@login_required
@require_POST
def read_notifications(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return redirect('questions:notifications')
