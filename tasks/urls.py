from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('auth/register/', views.register),
    path('auth/login/', views.login_view),
    path('auth/logout/', views.logout_view),
    path('auth/me/', views.me),
    path('auth/profile/', views.update_profile),
    path('auth/avatar/', views.upload_avatar),
    path('auth/stats/', views.account_stats),

    # Tasks
    path('tasks/', views.tasks_list),
    path('tasks/reorder/', views.task_reorder),
    path('tasks/categories/', views.task_categories_list),
    path('tasks/categories/<int:pk>/', views.task_category_detail),
    path('tasks/<int:pk>/', views.task_detail),
    path('tasks/<int:pk>/complete/', views.task_complete),
    path('tasks/<int:pk>/restore/', views.task_restore),
    path('tasks/<int:pk>/subtasks/', views.subtasks_list),
    path('tasks/treasure/delete-all/', views.delete_all_treasure),

    # Files
    path('files/', views.files_list),
    path('files/folders/', views.file_folders_list),
    path('files/folders/<int:pk>/', views.file_folder_detail),
    path('files/<int:pk>/', views.file_delete),
    path('files/<int:pk>/proxy/', views.file_proxy),

    # Notes
    path('notes/', views.notes_list),
    path('notes/folders/', views.note_folders_list),
    path('notes/folders/<int:pk>/', views.note_folder_detail),
    path('notes/<int:pk>/', views.note_detail),

    # Routine
    path('routine/tasks/', views.routine_tasks_list),
    path('routine/reorder/', views.routine_reorder),
    path('routine/streaks/', views.routine_streaks),
    path('routine/tasks/<int:pk>/', views.routine_task_detail),
    path('routine/today/', views.routine_today),
    path('routine/logs/<int:pk>/toggle/', views.routine_log_toggle),
    path('routine/history/', views.routine_history),
    path('routine/history/delete/', views.routine_delete_history),

    # Transactions
    path('transactions/categories/', views.categories_list),
    path('transactions/categories/<int:pk>/', views.category_detail),
    path('transactions/', views.transactions_list),
    path('transactions/charts/', views.transaction_charts),
    path('transactions/history/', views.transactions_history),
    path('transactions/<int:pk>/', views.transaction_detail),
    path('transactions/<int:pk>/restore/', views.transaction_restore),
    path('transactions/<int:pk>/permanent/', views.transaction_permanent_delete),
    path('transactions/delete-all/', views.transactions_delete_all),

    # Search
    path('search/', views.global_search),

    # Export
    path('export/tasks/', views.export_tasks),
    path('export/transactions/', views.export_transactions),
    path('export/notes/', views.export_notes),
    path('export/backup/', views.export_full_backup),

    # Admin
    path('admin/users/', views.admin_users),

    # Cron
    path('cron/send-reminders/', views.cron_send_reminders),
]