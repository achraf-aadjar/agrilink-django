from django.contrib import admin
from django.urls import path
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.landing, name='landing'),
    path('auth/', views.auth, name='auth'),
    path('logout/', views.logout, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('marketplace/', views.marketplace, name='marketplace'),
    path('marketplace/new/', views.listing_new, name='listing_new'),
    path('marketplace/<int:pk>/', views.listing_detail, name='listing_detail'),
    path('credit/', views.credit_index, name='credit'),
    path('credit/apply/', views.credit_apply, name='credit_apply'),
    path('assurance/', views.insurance_index, name='insurance'),
    path('assurance/new/', views.insurance_new, name='insurance_new'),
    path('conseiller/', views.conseiller, name='conseiller'),
    path('api/conseiller/', views.conseiller_api, name='conseiller_api'),
    path('profil/', views.profil, name='profil'),
]
