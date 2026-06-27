from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('auth/register/', views.register),
    path('auth/login/', views.login_view),
    path('auth/logout/', views.logout_view),
    path('auth/me/', views.me),
    path('auth/profile/', views.update_profile),

    # Tasks
    path('tasks/', views.tasks_list),
    path('tasks/<int:pk>/', views.task_detail),
    path('tasks/<int:pk>/complete/', views.task_complete),
    path('tasks/<int:pk>/restore/', views.task_restore),
    path('tasks/treasure/delete-all/', views.delete_all_treasure),

    # Files
    path('files/', views.files_list),
    path('files/<int:pk>/', views.file_delete),
    path('files/<int:pk>/proxy/', views.file_proxy),

    # Notes
    path('notes/', views.notes_list),
    path('notes/<int:pk>/', views.note_detail),

    # Routine
    path('routine/tasks/', views.routine_tasks_list),
    path('routine/tasks/<int:pk>/', views.routine_task_detail),
    path('routine/today/', views.routine_today),
    path('routine/logs/<int:pk>/toggle/', views.routine_log_toggle),
    path('routine/history/delete/', views.routine_delete_history),

    # Transactions
    path('transactions/categories/', views.categories_list),
    path('transactions/categories/<int:pk>/', views.category_detail),
    path('transactions/', views.transactions_list),
    path('transactions/<int:pk>/', views.transaction_detail),
    path('transactions/delete-all/', views.transactions_delete_all),

    # Admin
    path('admin/users/', views.admin_users),

    # Cron
    path('cron/send-reminders/', views.cron_send_reminders),
]