from django.contrib import admin
from .models import Tag, Question, Comment, QuestionLike, CommentLike, Reputation, Notification

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ('title','author','created_at')
    search_fields = ('title','body')
    list_filter = ('created_at',)

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('author','question','is_accepted','created_at')
    list_filter = ('is_accepted',)

admin.site.register([Tag, QuestionLike, CommentLike, Reputation, Notification])
