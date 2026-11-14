from django.contrib import admin
from .models import Tag, Question, Answer, QuestionVote, AnswerVote

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "created_at", "view_count")
    search_fields = ("title", "body")
    list_filter = ("created_at",)
    filter_horizontal = ("tags",)

@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("id", "question", "author", "created_at")

admin.site.register(QuestionVote)
admin.site.register(AnswerVote)
