from django.contrib import admin 
from django.urls import path 
from . import views 
from django.contrib.auth import views as auth_views 
 
urlpatterns = [ 
    path('admin/', admin.site.urls), 
    path('',views.indexpage,name='indexpage'), 
    path('dashboard/',views.dashboard,name='dashboard'),
    path('leadfiles/',views.leadfiles,name='leadfiles'),
    path('api/upload-lead-file/', views.upload_lead_file, name='upload_lead_file'),
    path('api/allocate-leads/', views.allocate_leads, name='allocate_leads'),
    path('api/lead-files/', views.get_lead_files, name='get_lead_files'),
    path('api/users/', views.get_users, name='get_users'),
    path('api/delete-file/<int:file_id>/', views.delete_file, name='delete_file'),
    path('dashboard-user/',views.dashboard2,name='dashboard2'),
    path('archieve/',views.archieve,name='archieve'),
    path('user-task/',views.usertask,name='usertask'),
    path('follow-ups/',views.followsup,name='followsup'),
    path('update_call_record/', views.update_call_record, name='update_call_record'),
    path('delete_call_record/', views.delete_call_record, name='delete_call_record'),
    path('update-call-record2/', views.update_call_record2, name='update_call_record2'),
    path('delete-call-record2/', views.delete_call_record2, name='delete_call_record2'),
    path('logout/',views.logouts,name="logout"),
    path('recording/',views.recordings_dashboard,name="recordings_dashboard"),




    #api
        path('api/login/', views.login_api, name='api-login'),
        path("api/logout/", views.logout_api,name='api-logout'),
        path('api/upload-recording/', views.upload_recording, name='upload-recording'),

    
] 