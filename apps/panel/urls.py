from django.urls import path
from apps.panel import views

urlpatterns = [
    path('', views.lista_tareas, name='lista_tareas'),
    path('tarea/<int:pk>/', views.detalle_tarea, name='detalle_tarea'),
    path('aprobar/', views.aprobar_tarea, name='aprobar_tarea'),
    path('login/', views.login_panel, name='login_panel'),
    path('logout/', views.logout_panel, name='logout_panel'),
    path('configuracion/', views.configuracion, name='configuracion'),
    path('configuracion/proveedor/nuevo/', views.crear_proveedor, name='crear_proveedor'),
    path('configuracion/modelo/nuevo/', views.crear_modelo, name='crear_modelo'),
]
