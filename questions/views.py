from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from .forms import AnswerForm, QuestionForm
from .models import Answer, AnswerVote, Question, QuestionVote, Tag


def question_list(request):
    questions = Question.objects.select_related("author", "accepted_answer").prefetch_related("tags").annotate(answer_total=Count("answers", distinct=True))
    search = request.GET.get("q", "").strip()[:150]
    tag = request.GET.get("tag", "").strip()[:60]
    status = request.GET.get("status", "newest")
    if search:
        questions = questions.filter(Q(title__icontains=search) | Q(body__icontains=search) | Q(tags__name__icontains=search)).distinct()
    if tag:
        questions = questions.filter(tags__slug=tag)
    if status == "unanswered":
        questions = questions.filter(answer_total=0)
    elif status == "solved":
        questions = questions.filter(accepted_answer__isnull=False)
    elif status == "unsolved":
        questions = questions.filter(accepted_answer__isnull=True)
    questions = questions.order_by("-created_at")
    from django.core.paginator import Paginator
    page = Paginator(questions, 15).get_page(request.GET.get("page"))
    return render(request, "questions/list.html", {"page": page, "search": search, "tag": tag, "status": status, "popular_tags": Tag.objects.annotate(total=Count("questions")).order_by("-total")[:20]})


def question_detail(request, pk):
    question = get_object_or_404(Question.objects.select_related("author", "accepted_answer").prefetch_related("tags"), pk=pk)
    Question.objects.filter(pk=pk).update(view_count=F("view_count") + 1)
    answers = question.answers.select_related("author").order_by("created_at")
    return render(request, "questions/detail.html", {"question": question, "answers": answers, "answer_form": AnswerForm()})

@login_required
def question_create(request):
    form = QuestionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            question = form.save(commit=False)
            question.author = request.user
            question.save()
            form.save_tags(question)
        messages.success(request, "Question posted successfully.")
        return redirect("questions:detail", pk=question.pk)
    return render(request, "questions/form.html", {"form": form, "heading": "Ask a question"})

@login_required
def question_edit(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if question.author_id != request.user.pk:
        raise PermissionDenied
    form = QuestionForm(request.POST or None, instance=question, initial={"tag_names": ", ".join(question.tags.values_list("name", flat=True))})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()
            form.save_tags(question)
        messages.success(request, "Question updated.")
        return redirect("questions:detail", pk=pk)
    return render(request, "questions/form.html", {"form": form, "heading": "Edit question"})

@login_required
@require_POST
def question_delete(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if question.author_id != request.user.pk:
        raise PermissionDenied
    question.delete()
    messages.success(request, "Question deleted.")
    return redirect("questions:list")

@login_required
@require_POST
def answer_create(request, pk):
    question = get_object_or_404(Question, pk=pk)
    form = AnswerForm(request.POST)
    if form.is_valid():
        answer = form.save(commit=False)
        answer.question = question
        answer.author = request.user
        answer.save()
        messages.success(request, "Answer posted.")
    else:
        messages.error(request, "Your answer needs at least 10 characters.")
    return redirect("questions:detail", pk=pk)

@login_required
def answer_edit(request, pk):
    answer = get_object_or_404(Answer.objects.select_related("question"), pk=pk)
    if answer.author_id != request.user.pk:
        raise PermissionDenied
    form = AnswerForm(request.POST or None, instance=answer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Answer updated.")
        return redirect("questions:detail", pk=answer.question_id)
    return render(request, "questions/form.html", {"form": form, "heading": "Edit answer"})

@login_required
@require_POST
def answer_delete(request, pk):
    answer = get_object_or_404(Answer, pk=pk)
    if answer.author_id != request.user.pk:
        raise PermissionDenied
    question_id = answer.question_id
    answer.delete()
    messages.success(request, "Answer deleted.")
    return redirect("questions:detail", pk=question_id)

@login_required
@require_POST
def accept_answer(request, pk):
    with transaction.atomic():
        answer = get_object_or_404(Answer, pk=pk)
        question = Question.objects.select_for_update().get(pk=answer.question_id)
        if question.author_id != request.user.pk:
            raise PermissionDenied
        question.accepted_answer = None if question.accepted_answer_id == answer.pk else answer
        question.full_clean()
        question.save(update_fields=["accepted_answer", "updated_at"])
    return redirect("questions:detail", pk=answer.question_id)

@login_required
@require_POST
def vote_question(request, pk):
    question = get_object_or_404(Question, pk=pk)
    if question.author_id == request.user.pk:
        raise PermissionDenied
    _vote(request, QuestionVote, "question", question)
    return redirect("questions:detail", pk=pk)

@login_required
@require_POST
def vote_answer(request, pk):
    answer = get_object_or_404(Answer, pk=pk)
    if answer.author_id == request.user.pk:
        raise PermissionDenied
    _vote(request, AnswerVote, "answer", answer)
    return redirect("questions:detail", pk=answer.question_id)

def _vote(request, model, field, target):
    try:
        value = int(request.POST.get("value", ""))
    except (ValueError, TypeError):
        raise Http404("Invalid vote")
    if value not in (-1, 1):
        raise Http404("Invalid vote")
    with transaction.atomic():
        existing = model.objects.select_for_update().filter(**{field: target, "user": request.user}).first()
        if existing:
            if existing.value == value:
                existing.delete()
            else:
                existing.value = value
                existing.save(update_fields=["value"])
        else:
            model.objects.create(**{field: target, "user": request.user, "value": value})
